import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper, without
from app.utils.logger import get_logger

logger = get_logger(__name__)

# A teaser's photo is a link of its own, with the photo's credit inside it ("Saul Loeb / AFP via Getty"): about 570
# credits were kept as headlines until Oct 28
PHOTO_PARTS = '[data-testid="image-credit"]'


class NBC(Scraper):
    url: str = 'https://www.nbcnews.com'
    agency: str = "NBC News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a',
                               {'href': re.compile(r"https://www.nbcnews.com/[a-z-]+/[a-z-]+/[a-z-]+")}):
            if '/select/' in a['href']:
                continue
            href = a['href']
            self.downstream.append((href, without(a, PHOTO_PARTS)))
