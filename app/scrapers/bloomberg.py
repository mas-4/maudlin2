import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Bloomberg(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.bloomberg.com'
    agency: str = "Bloomberg"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', { 'href': re.compile(".*/articles/.*")}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
