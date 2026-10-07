import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NewYorker(Scraper):
    url: str = 'https://www.newyorker.com'
    agency: str = "New Yorker"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/news/')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
