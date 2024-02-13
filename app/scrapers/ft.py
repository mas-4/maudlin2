import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class FT(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.ft.com'
    agency: str = "Financial Times"
    country = Country.gb

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/content/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
