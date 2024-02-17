import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class News18(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.news18.com/'
    agency: str = "News 18"
    country = Country.in_

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.BUNCH_OF_NUMBERS_DOT_HTML}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
