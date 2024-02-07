import argparse

from app.config import Config
from app.logger import get_logger
from app.registry import Scrapers
from app.site_builder import build_site

logger = get_logger(__name__)


class Queue:
    def __init__(self):
        self.scrapers = []

    def run(self):
        for scraper in self.scrapers:
            scraper.start()
        
        for scraper in self.scrapers:
            scraper.join()

    def add(self, scraper):
        self.scrapers.append(scraper())


def scrape():
    queue = Queue()
    logger.info("Initializing queue")
    logger.info("Scrapers: %s", Scrapers)
    for scraper in Scrapers:
        queue.add(scraper)

    queue.run()

def main(args: argparse.Namespace):  # noqa shadowing
    if args.scraper:
        scraper = [s for s in Scrapers if s.agency == args.scraper]
        if len(scraper) == 0:
            raise ValueError(f"Scraper {args.scraper} not found")
        sc = scraper[0]()
        sc.start()
        sc.join()
        return
    if not args.skip_scrape:
        scrape()
    build_site()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dev', action='store_true')
    parser.add_argument('--skip-scrape', action='store_true')
    parser.add_argument('--scraper', type=str, default=None)
    args = parser.parse_args()
    Config.dev_mode = args.dev
    main(args)
