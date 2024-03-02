import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RollingStone(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://www.rollingstone.com/'
    agency: str = "Rolling Stone"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'-\d+/?$')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
