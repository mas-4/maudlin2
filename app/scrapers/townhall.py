from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, Constants, get_logger

logger = get_logger(__name__)


class Townhall(Scraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://townhall.com'
    agency: str = "Townhall"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
