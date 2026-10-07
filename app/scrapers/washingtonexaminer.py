import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils import get_logger

logger = get_logger(__name__)


class WashingtonExaminer(SeleniumScraper):
    url: str = 'https://www.washingtonexaminer.com/'
    agency: str = "Washington Examiner"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/news/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
