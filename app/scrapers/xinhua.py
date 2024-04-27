import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Xinhua(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://english.news.cn/'
    agency: str = "Xinhua"
    country = Country.cn

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{8}/')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
