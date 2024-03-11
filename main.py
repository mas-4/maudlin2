import argparse

from app.utils.config import Config
from app.utils.logger import get_logger
from app.analysis.topics import analyze_all_topics
from app.registry import Scrapers
from app.site_builder import build_site
from app.scraper import SeleniumScraper, SeleniumResourceManager
from utils.dayreport import DayReport

logger = get_logger(__name__)


class Queue:
    def __init__(self, args):
        self.threads = []
        self.seleniums = []
        self.args = args

    def run(self):
        logger.info("Running threads")
        for scraper in self.threads:
            scraper.start()

        if Config.run_selenium and self.args.run_selenium:
            logger.info("Running seleniums")
            for sel in self.seleniums:
                scraper = sel()
                try:
                    scraper.run()
                except Exception as e:
                    logger.exception(f"Failed to run {scraper}: {e}")
                    continue
            SeleniumResourceManager().quit()

        for scraper in self.threads:
            scraper.join()  # make sure to wait for everything to finish

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
    if args.analyze_topics:
        analyze_all_topics()
        return
    if args.email_report:
        DayReport.report_turnover()
        return
    if not args.skip_scrape:
        scrapers = [s for s in Scrapers if s.agency == args.scraper] if args.scraper else Scrapers
        scrape(args, scrapers)
    build_site()


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--skip-scrape', action='store_true')
    parser.add_argument('--scraper', type=str, default=None)
    parser.add_argument('--email-report', action='store_true')
    parser.add_argument('--run-selenium', action='store_true')
    parser.add_argument('--analyze-topics', action='store_true')
    args = parser.parse_args()
    Config.dev_mode = args.dev
    return args


if __name__ == '__main__':
    main(get_args())
