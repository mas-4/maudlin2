import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils import get_logger

logger = get_logger(__name__)


class Bulwark(SeleniumScraper):
    url: str = 'https://www.thebulwark.com/'
    agency: str = "The Bulwark"
    ready: str = 'a[href*="/p/"]'  # its article links are drawn by scripts after the page loads

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/p/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
