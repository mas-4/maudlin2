import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class RedState(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.low
    url: str = 'https://redstate.com'
    agency: str = "Red State"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href =  a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

