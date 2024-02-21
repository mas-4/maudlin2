from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Economist(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.economist.com'
    agency: str = "The Economist"
    country: Country = Country.gb

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            if not href.startswith('http'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

