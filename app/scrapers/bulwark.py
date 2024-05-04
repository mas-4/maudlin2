import re
from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, Constants, get_logger
from app.scraper import SeleniumScraper

logger = get_logger(__name__)


class Bulwark(SeleniumScraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://www.thebulwark.com/'
    agency: str = "The Bulwark"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/p/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

