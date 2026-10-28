import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper, without
from app.utils.logger import get_logger

logger = get_logger(__name__)

# A story's photo is a link of its own with the credit laid over the picture ("Jim Watson/AFP via Getty Images"):
# about 160 were kept as headlines until Oct 28
PHOTO_PARTS = '[data-testid="prism-indicator"]'


class ABC(Scraper):
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
                self.downstream.append((href, without(a, PHOTO_PARTS)))
