import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.analysis import newsfilter
from app.analysis.metrics import reapply_sent
from app.analysis.preprocessing import reprocess_headlines
from app.analysis.topics import analyze_all_topics
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
                continue
            else:
                self.scrapers.append(scraper)
        SeleniumResourceManager().quit()
        logger.info(f"Finished seleniums in {time.time() - t} seconds")

    def post_run(self):
        num = len(self.scrapers)
        for i, sel in enumerate(self.scrapers):
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
                if scraper.success:
                    scraper.post_run()
                    logger.info(f"Finished {scraper} ({i + 1} of {num})")

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
    if args.email_newsletter:
        with open(Config.newsletter, 'rt') as f:
            send_notification(f.read())
        return
    if not args.skip_scrape:
        scrapers = [s for s in Scrapers if s.agency == args.scraper] if args.scraper else Scrapers
        scrape(args, scrapers)
        if not args.scraper:
            fetch_trends()
            fetch_investigations()
            wiki.refresh()  # weekly: each outlet's Wikipedia opening and Wikidata facts
            fetch_sidefeeds()  # newsletters, podcasts and political video channels, each at most every 2 hours
            fetch_polls()
            fetch_aggregates()
    build()
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
    parser.add_argument('--debug', action='store_true')
    args = parser.parse_args()
    if args.debug:
        Config.set_debug()
    return args


if __name__ == '__main__':
    main(get_args())
