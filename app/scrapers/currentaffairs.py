import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CurrentAffairs(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://www.currentaffairs.org'
    agency: str = "Current Affairs"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/')}):
            if a['href'].startswith('http'):
                continue
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
