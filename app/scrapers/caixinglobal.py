import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class CaixinGlobal(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.caixinglobal.com'
    agency: str = "Caixin Global"
    country = Country.cn

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/\d{4}-\d{2}-\d{2}/.*')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

