import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Bloomberg(Scraper):
    url: str = 'https://www.bloomberg.com'
    agency: str = "Bloomberg"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(".*/articles/.*")}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
