import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Economist(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.economist.com'
    agency: str = "The Economist"
    country: Country = Country.gb

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = a['href']
            if not href.startswith('http'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

