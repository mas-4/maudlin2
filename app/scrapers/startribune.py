import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class StarTribune(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.startribune.com'
    agency: str = "Star Tribune"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/\d+/$')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

