from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Fortune(Scraper):
    url: str = 'https://fortune.com'
    agency: str = "Fortune"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
