import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MotherJones(Scraper):
    url: str = 'https://www.motherjones.com'
    agency: str = "Mother Jones"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/')}):
            href = a['href']
            if not href.startswith('http'):
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
