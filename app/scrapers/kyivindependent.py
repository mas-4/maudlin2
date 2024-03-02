import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class KyivIndependent(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://kyivindependent.com'
    agency: str = "The Kyiv Independent"
    country = Country.ua

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'rel': 'dofollow', 'href': re.compile(r'^/.*')}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
