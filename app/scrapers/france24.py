import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class France24(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.france24.com/en'
    agency: str = "France24"
    country: Country = Country.fr

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/en/.*/\d{8}-.*')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
