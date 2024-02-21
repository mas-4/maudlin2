import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Sun(Scraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://www.the-sun.com/'
    agency: str = "The Sun"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': re.compile(r'/news/\d+/')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

