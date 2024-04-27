import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NikkeiAsia(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://asia.nikkei.com'
    agency: str = "Nikkei Asia"
    country: str = Country.jp

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-trackable': re.compile(r'headline|title'), 'href': True}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
