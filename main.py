from app.registry import Scrapers
from app.logger import get_logger
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

def main():
    scrape()
    build_site()


if __name__ == '__main__':
    main()
