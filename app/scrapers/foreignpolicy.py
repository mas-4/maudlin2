import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class ForeignPolicy(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://foreignpolicy.com/'
    agency: str = "Foreign Policy"
    strip: list[str] = []
    headline_only = True


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        pass  # headline only


