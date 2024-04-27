import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RT(Scraper):
    bias = Bias.right_center
    credibility = Credibility.very_low
    url: str = 'https://www.rt.com'
    agency: str = "RT"
    country: str = Country.ru

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/(russia|news)/.+')}):
            href = a['href']
            self.downstream.append((href, a))
