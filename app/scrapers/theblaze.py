import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class TheBlaze(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.mixed
    url: str = 'https://www.theblaze.com'
    agency: str = "The Blaze"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': re.compile('headline')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

