import re

from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, Constants, get_logger
from app.scraper import SeleniumScraper

logger = get_logger(__name__)


class MarketWatch(SeleniumScraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://www.marketwatch.com/'
    agency: str = "MarketWatch"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/story/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

