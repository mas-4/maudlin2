import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class AP(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://apnews.com/'
    agency: str = "AP"

    def setup(self, soup: Soup):
        for a in soup.find('main', {'class': 'Page-oneColumn'}).find_all(
                'a', { 'href': re.compile(".*/article/.*")}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
