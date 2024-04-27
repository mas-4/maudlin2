from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VanityFair(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://www.vanityfair.com/'
    agency: str = "Vanity Fair"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-component-type': 'recirc-river'}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
