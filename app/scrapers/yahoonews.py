import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class YahooNews(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://news.yahoo.com/'
    agency: str = "Yahoo News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'-\d+\.html')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
