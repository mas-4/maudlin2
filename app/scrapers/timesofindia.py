import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TimesofIndia(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://timesofindia.indiatimes.com/us'
    agency: str = "The Times of India"
    country = Country.in_

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d+\.cms')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
