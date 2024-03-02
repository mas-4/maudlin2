import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CrooksandLiars(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://crooksandliars.com'
    agency: str = "Crooks and Liars"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/\d{4}/\d{2}/.*')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
