import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Jacobin(Scraper):
    bias = Bias.extreme_left
    credibility = Credibility.high
    url: str = 'https://jacobin.com'
    agency: str = "Jacobin"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/')}):
            href = a['href']
            if not href.startswith('https://'):  # catalyst-journal.com links? what are they
                href = self.url + href
            else:
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
