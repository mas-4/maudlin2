import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class MilitaryCom(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.military.com'
    agency: str = "Military.com"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = self.url + a['href']
            title = a.find('span', {'property': 'schema:name'})
            if title:
                self.downstream.append((href, title.text.strip()))

