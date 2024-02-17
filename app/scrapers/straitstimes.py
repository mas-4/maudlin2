import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class StraitsTimes(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.straitstimes.com/global'
    agency: str = "The Straits Times"
    country = Country.sg
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': 'stretched-link'}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

