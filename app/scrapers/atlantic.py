import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Atlantic(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.theatlantic.com/'
    agency: str = "The Atlantic"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/archive/\d{4}/\d{2}/.*')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

