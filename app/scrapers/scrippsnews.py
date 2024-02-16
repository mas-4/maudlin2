import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class ScrippsNews(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://scrippsnews.com/'
    agency: str = "Scripps News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': 'link-target'}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

