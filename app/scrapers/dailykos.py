import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DailyKos(Scraper):
    bias = Bias.extreme_left
    credibility = Credibility.mixed
    url: str = 'https://www.dailykos.com'
    agency: str = "The Daily Kos"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')}):
            h3 = a.find('h3')
            if not h3:
                continue
            href = a['href']
            if not href.startswith('http'):
                href = f'{self.url}{href}'
            self.downstream.append((href, h3))
