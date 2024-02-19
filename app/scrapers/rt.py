import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

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
            title = a.text.strip()
            self.downstream.append((href, title))

