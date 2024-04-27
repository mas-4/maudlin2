from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NationalInterest(SeleniumScraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://nationalinterest.org/'
    agency: str = "The National Interest"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DASH_BUNCH_OF_NUMBERS}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
