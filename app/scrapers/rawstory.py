import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class RawStory(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://www.rawstory.com'
    agency: str = "Raw Story"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'aria-label': True}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

