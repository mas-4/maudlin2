import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils import get_logger

logger = get_logger(__name__)


class Nation(SeleniumScraper):
    url: str = 'https://www.thenation.com/'
    agency: str = "The Nation"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/article/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
