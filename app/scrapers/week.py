import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Week(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://theweek.com/'
    agency: str = "The Week"

    def setup(self, soup: Soup):
        main = soup.find('div', {'id': 'main'})
        for a in main.find_all('a', {'href': re.compile(r'-\d{4}-\d{2}-\d{2}-\d+')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

        for a in main.find_all('a', {'class': 'listing__link'}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

