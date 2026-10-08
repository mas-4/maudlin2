import argparse
import os
import sys
from datetime import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.analysis import newsfilter
from app.analysis.metrics import reapply_sent
from app.analysis.preprocessing import reprocess_headlines
from app.analysis.topics import analyze_all_topics
from app import scraper_health
from app.registry import Scrapers
from app.scraper import SeleniumScraper, SeleniumResourceManager, Scraper
from app.trends import fetch_trends
from app.investigations import fetch_investigations
from app.site import wiki
from app.sidefeeds import fetch_sidefeeds
from app.polling import fetch_polls, fetch_aggregates
from app.builder import build
from app.utils import Config, get_logger
from utils.emailer import send_notification
import threading

logger = get_logger(__name__)
NARRATIVE_HOUR = 4  # the run that writes the day's narrative report
SHOW_BUDGET = 420  # seconds a run spends reading the shows' transcripts for claims (about 280 parts a day at ~35 s)
FOCUS_BUDGET = 180  # seconds a run spends reading new Focus Group episodes (one a week, about a minute and a half)
RUNNING_BUDGET = 120  # seconds a run spends splitting the radio newscasts into their stories (two an hour)
CHYRON_BUDGET = 180  # seconds a run spends cleaning TV chyron OCR (about 45 minutes of work a day)
MOTIF_BUDGET = 300  # seconds a run spends filing claims in the motif index
FIT_BUDGET = 240  # seconds a run spends scoring new filings (reranker and a yes/no from the filing model per filing)
PROPOSAL_HOUR = 5  # the motif proposer's nightly run: after the 4 AM report and its first filings
TEACH_HOUR = 1  # the weekly reranker teaching starts in this hour's run (done by the 4 AM report)


def teaching() -> bool:
    """Whether a reranker teaching is still running (one at a time)"""
    import subprocess
    return subprocess.run(['pgrep', '-f', '[a]pp.analysis.reranker_teach'], capture_output=True).returncode == 0
QUIET_MINUTES = 16  # a long job (a rescore) leaves the gpu to the hourly run for its first minutes


class SeleniumThread(threading.Thread):
    def __init__(self, seleniums):
        self.seleniums = seleniums
        threading.Thread.__init__(self)
        self.scrapers = []

    def run(self):
        t = time.time()
        for sel in self.seleniums:
            scraper = sel()
            try:
                scraper.run()
            except Exception as e:
                logger.error(f"Failed to run {scraper}: {e}")
                scraper_health.record(scraper.agency, scraper.url, error=type(e).__name__)
                continue
            else:
                self.scrapers.append(scraper)
        SeleniumResourceManager().quit()
        logger.info(f"Finished seleniums in {time.time() - t} seconds")

    def post_run(self):
        num = len(self.scrapers)
        for i, sel in enumerate(self.scrapers):
            if not sel.success:  # its page never loaded
                scraper_health.record(sel.agency, sel.url, error='page not loaded')
                continue
            sel.post_run()
            logger.info(f"Finished {sel} ({i + 1} of {num})")


class Queue:
    def __init__(self, args):
        self.threads = []
        self.seleniums = []
        self.args = args

    def run(self):
        seleniumthread = SeleniumThread(self.seleniums)
        if Config.run_selenium and self.args.run_selenium:
            logger.info("Running seleniums")
            seleniumthread.start()

        num = len(self.threads)
        with ThreadPoolExecutor(max_workers=Config.max_threads) as executor:
            futures = {executor.submit(scraper.run): scraper for scraper in self.threads}
            for i, future in enumerate(as_completed(futures)):
                scraper: Scraper = futures[future]
                if future.exception():
                    scraper_health.record(scraper.agency, scraper.url, error=type(future.exception()).__name__)
                elif scraper.success:
                    scraper.post_run()
                    logger.info(f"Finished {scraper} ({i + 1} of {num})")
                else:
                    scraper_health.record(scraper.agency, scraper.url, error='page not loaded')

        if Config.run_selenium and self.args.run_selenium:
            logger.info("Waiting for seleniums")
            seleniumthread.join()
            seleniumthread.post_run()

    def add(self, scraper):
        if issubclass(scraper, SeleniumScraper):
            self.seleniums.append(scraper)
        else:
            self.threads.append(scraper())


def scrape(args, scrapers):
    if not len(scrapers):
        raise ValueError("No scrapers provided")
    queue = Queue(args)
    logger.info("Initializing queue")
    logger.info("Scrapers: %s", scrapers)
    for scraper in scrapers:
        queue.add(scraper)

    queue.run()
    # The list of scrapers to check (data/scraper_check.md); browser-driven ones only when they ran
    ran_seleniums = Config.run_selenium and args.run_selenium
    scraper_health.write([(s.agency, s.url) for s in scrapers if ran_seleniums or not issubclass(s, SeleniumScraper)])


def between_runs():
    """Block while the hourly run has (or is about to have) the gpu: its first QUIET_MINUTES, the minutes before it,
    and while it runs."""
    import subprocess
    while True:
        # A one-shot job is "activating" while it runs, never "active" (so is-active can't tell): anything but inactive
        state = subprocess.run(['systemctl', 'show', '-p', 'ActiveState', '--value', 'maudlin-scrape.service'],
                               capture_output=True, text=True).stdout.strip()
        running = state not in ('inactive', 'failed', '')
        if not running and QUIET_MINUTES <= dt.now().minute < 58:  # a chunk started at :58 ends before :00
            return
        time.sleep(60)


def main(args: argparse.Namespace):
    t = time.time()
    if args.analyze_topics:
        analyze_all_topics(True)
        return
    if args.analyze_sentiment is not None:
        reapply_sent('all' in args.analyze_sentiment)
        return
    if args.reprocess is not None:
        reprocess_headlines('all' in args.reprocess)
        return
    if args.label_headlines:
        newsfilter.label_headlines(args.label_headlines)
        return
    if args.train_newsfilter:
        newsfilter.train()
        return
    if args.rescore_news or args.rescore_missing:
        newsfilter.rescore_all(only_missing=args.rescore_missing)
        return
    if args.rescore_outdated:
        newsfilter.rescore_all(outdated=True, wait=between_runs)
        return
    if args.email_newsletter:
        with open(Config.newsletter) as f:
            send_notification(f.read())
        return
    # What people say on Bluesky and Mastodon (research only, #153): sampled on a thread of its own while the outlets are
    # scraped and the site builds, so it adds no time to the run
    listening = None
    if not args.skip_scrape and not args.scraper and not Config.debug:
        from app import vernacular
        listening = threading.Thread(target=lambda: (vernacular.sample(), vernacular.mastodon_sample()), daemon=True)
        listening.start()
    if not args.skip_scrape:
        scrapers = [s for s in Scrapers if s.agency == args.scraper] if args.scraper else Scrapers
        scrape(args, scrapers)
        if not args.scraper:
            fetch_trends()
            fetch_investigations()
            wiki.refresh()  # weekly: each outlet's Wikipedia opening and Wikidata facts
            fetch_sidefeeds()  # newsletters, podcasts and political video channels, each at most every 2 hours
            try:  # the shows' new episodes: on the news, or evergreen (history, life stories)
                from app import episode_kind
                episode_kind.label_new()
            except Exception as e:  # noqa: BLE001 - unlabeled episodes count as news
                logger.warning("Episode labels failed: %s", e)
            try:  # fact-checks' own text, for reading their claims from the piece, not the headline
                from app import sidefeeds as sf
                from app.analysis import factcheck_text, factchecks
                factcheck_text.gather(factchecks._items(factchecks.LABEL_DAYS), sf.SOURCES, budget=300)
            except Exception as e:  # noqa: BLE001 - labels fall back to the feed's blurb
                logger.warning("Fact-check texts failed: %s", e)
            try:
                from app import health
                health.check()  # every outlet and regular feed still coming in (warnings in the log, health.json)
            except Exception as e:  # noqa: BLE001 - the check is a lookout, never a reason to stop the run
                logger.warning("Health check failed: %s", e)
            from app.chyrons import fetch_chyrons
            fetch_chyrons()  # TV news chyrons from the Internet Archive: one request a run (today so far, UTC)
            fetch_polls()
            fetch_aggregates()
    build()
    if listening is not None:
        listening.join(timeout=10 * 60)  # five minutes of listening, begun with the scrape: usually already done
    if not args.skip_scrape and not args.scraper and not Config.debug:
        # The language model is done for this run: Whisper gets the GPU for up to ten minutes
        from app.transcribe import transcribe_pending
        transcribe_pending(budget=600)
        # Once a night, the day's narratives (research only, #142): the GPU has nothing else to do at 4 AM. If that
        # run was missed (Oct 5: the machine hung in sleep from 3 to 7), the next run after 4 AM makes up for it
        from app import narratives
        reported = False
        if dt.now().hour >= NARRATIVE_HOUR and not narratives.made_today():
            reported = True
            from app.analysis import circulation
            narratives.report(hours=24)
            from app.analysis import narrative_threads
            narrative_threads.link_days()  # the same narratives told on earlier days
            circulation.nightly()  # which fact-checked rumors people are telling or arguing over (#153)
        # New claims into our own motif index (#145), a few minutes a run with the bigger model, so a night with a
        # long report can't push a run past its time limit; what's left waits for the next run
        # What voters say in The Focus Group's episodes (#164), read once per episode with the bigger model
        from app.analysis import focus_group
        focus_group.extract(budget=FOCUS_BUDGET)
        # What's told on every show we transcribe, right, left and center (talk radio, call-ins, podcasts), never in
        # the report's run: it nears the 45-minute limit
        if not reported:
            from app.analysis import show_claims
            show_claims.extract(budget=SHOW_BUDGET)
        # The hourly radio newscasts' running order beside the front pages' (#159)
        from app.analysis import running_order
        running_order.read(budget=RUNNING_BUDGET)
        # TV chyrons: the OCR read into headlines, names, promos and ads, a few minutes a run
        from app import chyrons
        chyrons.clean_recent(budget=CHYRON_BUDGET)
        chyrons.match_recent()
        from app.analysis import motif_index
        motif_index.nightly(budget=MOTIF_BUDGET)
        # How sure each new filing is (its fit: many signals weighed on the person's own decisions), for the checker
        if not reported:  # never in the report's run: it nears the 45-minute limit
            from app.analysis import filing_confidence
            try:
                filing_confidence.refresh(budget=FIT_BUDGET)
            except Exception as e:  # noqa: BLE001 - the fits wait for the next run
                logger.warning("Filing confidence failed: %s", e)
            # Weekly at night: the reranker taught the person's latest decisions, on the CPU in a process of its own
            # (about two and a half hours at low priority; the next runs carry on beside it)
            if dt.now().hour == TEACH_HOUR:
                try:
                    from app.analysis import reranker_teach
                    if reranker_teach.due() and not teaching():
                        import subprocess
                        subprocess.Popen(['nice', '-n', '19', sys.executable, '-m', 'app.analysis.reranker_teach'],
                                         cwd=os.path.dirname(os.path.abspath(__file__)), start_new_session=True,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        logger.info("Reranker teaching started")
                except Exception as e:  # noqa: BLE001 - next week
                    logger.warning("Reranker teaching didn't start: %s", e)
        # Fixes for a person to approve in the workbench (typos, links, groups), once a day after the new filings
        if dt.now().hour >= PROPOSAL_HOUR and not reported:  # never in the report's run: it nears the 45-minute limit
            from app.analysis import motif_proposals
            motif_proposals.nightly()
    logger.info("Finished in %f minutes", round((time.time() - t) / 60, 2))


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-scrape', action='store_true')
    parser.add_argument('--scraper', type=str, default=None)
    parser.add_argument('--email-newsletter', action='store_true')
    parser.add_argument('--run-selenium', action='store_true')
    parser.add_argument('--analyze-topics', action='store_true')
    parser.add_argument('--analyze-sentiment', action='store', type=str)
    parser.add_argument('--reprocess', action='store', type=str)
    parser.add_argument('--label-headlines', type=int, default=0, metavar='N',
                        help='have the llm label N stored headlines as training data for the news filter')
    parser.add_argument('--train-newsfilter', action='store_true',
                        help='train the fallback news classifier on the labeled headlines')
    parser.add_argument('--rescore-news', action='store_true',
                        help='judge every stored headline again: news or not, event and loaded scores (uses the llm)')
    parser.add_argument('--rescore-missing', action='store_true',
                        help='judge only stored headlines that have no scores yet, e.g. after an interrupted run')
    parser.add_argument('--rescore-outdated', action='store_true',
                        help='judge again the headlines not scored by the current model and rubric, between hourly '
                             'runs (resumable)')
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        Config.set_debug()
    return args


if __name__ == '__main__':
    main(get_args())
