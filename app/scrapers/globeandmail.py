import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GlobeAndMail(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://www.theglobeandmail.com/'
    agency: str = "The Globe and Mail"
    country: Country = Country.ca

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/article-.*')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
