import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class KyivIndependent(Scraper):
    url: str = 'https://kyivindependent.com'
    agency: str = "The Kyiv Independent"
    country = Country.ua

    def setup(self, soup: Soup):
        # articles live at a top level slug like /russia-planning-to-increase-hybrid-warfare
        for a in soup.find_all('a', {'href': re.compile(r'^/[a-z0-9]+(-[a-z0-9]+){3,}/?$')}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
