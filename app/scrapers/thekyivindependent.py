import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class TheKyivIndependent(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://kyivindependent.com'
    agency: str = "The Kyiv Independent"
    country = Country.ua

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'rel': 'dofollow', 'href': re.compile(r'^/.*') }):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

