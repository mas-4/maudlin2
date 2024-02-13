import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class CNBC(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.cnbc.com'
    agency: str = "CNBC"
    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            if not href.startswith('http'):
                href = f'{self.url}{href}'
            if '/video/' in href:
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
