import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Time(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://time.com/'
    agency: str = "Time"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d+/.*')}):
            try:
                href = a['href']
                title = a.text.strip()
                if "Go to item" in title:
                    continue
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

