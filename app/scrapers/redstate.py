from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RedState(Scraper):
    url: str = 'https://redstate.com'
    agency: str = "Red State"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
