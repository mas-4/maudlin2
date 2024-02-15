import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NewRepublic(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://newrepublic.com'
    agency: str = "New Republic"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/post/\d+/')}):
            href = self.url + a['href']
            title = a.find('div', class_='Hed')
            if title:
                self.downstream.append((href, title.text.strip()))

