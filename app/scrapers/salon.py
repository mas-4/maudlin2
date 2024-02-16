import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import SeleniumScraper

logger = get_logger(__name__)


class Salon(SeleniumScraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.salon.com'
    agency: str = "Salon"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            elif href.startswith('20'):
                href = self.url + '/' + href
            else:
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

