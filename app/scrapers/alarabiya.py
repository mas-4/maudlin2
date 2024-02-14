import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class AlArabiya(Scraper):  # Disabled 403
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://english.alarabiya.net'
    agency: str = "Al Arabiya"
    country = Country.sa


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'title': True}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

