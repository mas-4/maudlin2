import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Blaze(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.mixed
    url: str = 'https://www.theblaze.com'
    agency: str = "The Blaze"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': re.compile('headline')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
