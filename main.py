import argparse

from app.utils.config import Config
from app.utils.logger import get_logger
from app.registry import Scrapers
from app.site_builder import build_site
from app.scraper import SeleniumScraper, SeleniumResourceManager
from app.dayreport import DayReport

logger = get_logger(__name__)


class Queue:
    def __init__(self):
        self.threads = []
        self.seleniums = []

    def run(self):
        logger.info("Running threads")
        for scraper in self.threads:
            scraper.start()
        
        for scraper in self.threads:
            scraper.join()

        if Config.run_selenium:
            logger.info("Running seleniums")
            for sel in self.seleniums:
                scraper = sel()
                scraper.run()
            SeleniumResourceManager().quit()

    def add(self, scraper):
        if issubclass(scraper, SeleniumScraper):
            self.seleniums.append(scraper)
        else:
            self.threads.append(scraper())

def scrape(scrapers):
    if not len(scrapers):
        raise ValueError("No scrapers provided")
    queue = Queue()
    logger.info("Initializing queue")
    logger.info("Scrapers: %s", scrapers)
    for scraper in scrapers:
        queue.add(scraper)

    queue.run()

def main(args: argparse.Namespace):
    if args.email_report:
        DayReport.report_turnover()
        return
    if not args.skip_scrape:
        scrapers = [s for s in Scrapers if s.agency == args.scraper] if args.scraper else Scrapers
        scrape(scrapers)
    build_site()


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--skip-scrape', action='store_true')
    parser.add_argument('--scraper', type=str, default=None)
    parser.add_argument('--email-report', action='store_true')
    args = parser.parse_args()
    Config.dev_mode = args.dev
    return args


if __name__ == '__main__':
    main(get_args())
