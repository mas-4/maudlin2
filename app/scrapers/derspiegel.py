import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class DerSpiegel(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.spiegel.de/international'
    agency: str = "Der Spiegel"
    country = Country.de

    def setup(self, soup: Soup):
        for a in soup.find('section', {'aria-label': 'International'})\
                .find_all('a', {'title': True, 'href': True}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

