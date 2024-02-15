import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NikkeiAsia(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://asia.nikkei.com'
    agency: str = "Nikkei Asia"
    country: str = Country.jp

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-trackable': re.compile(r'headline|title'), 'href': True}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
