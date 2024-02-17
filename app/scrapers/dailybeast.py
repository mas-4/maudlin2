import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class DailyBeast(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.thedailybeast.com/'
    agency: str = "The Daily Beast"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': re.compile('TrackingLink')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

