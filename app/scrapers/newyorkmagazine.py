import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NewYorkMagazine(Scraper):
    url: str = 'https://nymag.com'
    agency: str = "New York Magazine"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'nymag.com/.*/article/')}):
            href = a['href']
            if href.startswith('//'):
                href = f'https:{href}'
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
