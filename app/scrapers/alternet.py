from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, get_logger

logger = get_logger(__name__)


class Alternet(Scraper):
    bias = Bias.extreme_left
    credibility = Credibility.mixed
    url: str = 'https://www.alternet.org/'
    agency: str = "Alternet"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'aria-label': True, 'href': True}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
