from app.registry import Scrapers
from app.logger import get_logger

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


def main():
    queue = Queue()
    logger.info("Initializing queue")
    logger.info("Scrapers: %s", Scrapers)
    for scraper in Scrapers:
        queue.add(scraper)

    queue.run()


if __name__ == '__main__':
    main()
