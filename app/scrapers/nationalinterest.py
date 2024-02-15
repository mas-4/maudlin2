import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NationalInterest(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://nationalinterest.org/'
    agency: str = "National Interest"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*-\d+')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

