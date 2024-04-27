from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, get_logger

logger = get_logger(__name__)


class WashingtonFreeBeacon(Scraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://freebeacon.com/'
    agency: str = "The Washington Free Beacon"

    def setup(self, soup: Soup):
        for a in soup.find('main').find_all('a'):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
