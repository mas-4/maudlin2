import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class ForeignAffairs(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.foreignaffairs.com'
    agency: str = "Foreign Affairs"

    def setup(self, soup: Soup):
        for a in soup.find('div', {'class': 'content'}
                           ).find_all('a', {'href': re.compile(r'^/.*/.*$')}):
            href = a['href']
            if not href.startswith('/'):
                continue
            href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
