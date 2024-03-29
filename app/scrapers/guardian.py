import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Guardian(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.theguardian.com/us'
    agency: str = "The Guardian"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\w{3}/\d{2}/'), 'aria-label': True}):
            try:
                href = a['href']
                title = a['aria-label']
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
