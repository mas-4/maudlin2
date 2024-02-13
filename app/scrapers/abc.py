import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class ABC(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://abcnews.go.com/'
    agency: str = "ABC News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/story\?id=')}):
            href = a['href']
            if h := a.find(['h1', 'h2', 'h3', 'h4']):
                title = h.text.strip()
            else:
                title = a.text.strip()
            if title:
                self.downstream.append((href, title))
