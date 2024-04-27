import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Breitbart(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.mixed
    url: str = 'https://www.breitbart.com/'
    agency: str = "Breitbart"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
