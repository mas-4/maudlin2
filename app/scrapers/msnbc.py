import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class MSNBC(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.msnbc.com'
    agency: str = "MSNBC"

    def setup(self, soup: Soup):
        header_end = soup.find('div', {'id': 'header-end'})
        main_content = header_end.find_next('div')
        for a in main_content.find_all('a'):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

