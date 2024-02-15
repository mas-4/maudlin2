import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NewYorker(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://www.newyorker.com/'
    agency: str = "The New Yorker"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/news/')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

