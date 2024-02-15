import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NewYorkPost(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://nypost.com'
    agency: str = "New York Post"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

