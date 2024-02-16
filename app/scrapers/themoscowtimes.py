import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class TheMoscowTimes(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.themoscowtimes.com'
    agency: str = "The Moscow Times"
    country: str = Country.ru

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

