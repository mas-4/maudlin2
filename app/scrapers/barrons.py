import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Barrons(Scraper):  # Disabled because they're assholes
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://www.barrons.com'
    agency: str = "Barron's"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/articles/')}):
            href = a['href']
            title = a.text.strip()
            self.downstream.append((href, title))
