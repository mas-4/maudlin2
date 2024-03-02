import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CBC(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.cbc.ca'
    agency: str = "CBC"
    country: str = Country.ca

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'^/news/')}):
            href = self.url + a['href']
            if not (title := a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'], {'class': 'headline'})):
                continue
            title = title.text.strip()
            if title:
                self.downstream.append((href, title))
