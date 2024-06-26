import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, get_logger

logger = get_logger(__name__)


class ProPublica(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.propublica.org/'
    agency: str = "ProPublica"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/article/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
