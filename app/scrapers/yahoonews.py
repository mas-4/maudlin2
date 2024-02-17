import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class YahooNews(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'http://news.yahoo.com/'
    agency: str = "Yahoo News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'-\d+\.html')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
