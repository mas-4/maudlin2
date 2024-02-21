import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class MotherJones(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.motherjones.com'
    agency: str = "Mother Jones"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/')}):
            href = a['href']
            if not href.startswith('http'):
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

