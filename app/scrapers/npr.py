from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NPR(Scraper):
    url: str = 'https://text.npr.org/'
    agency: str = "NPR"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', class_='topic-title'):
            href = self.url + a.get('href')[1:]
            self.downstream.append((href, a))
