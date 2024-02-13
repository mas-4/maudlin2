import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class HuffPost(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.huffpost.com/'
    agency: str = "HuffPost"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/entry/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
