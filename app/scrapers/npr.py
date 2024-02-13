from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

logger = get_logger(__name__)


class NPR(Scraper):
    url: str = 'https://text.npr.org/'
    agency: str = "NPR"
    bias: Bias = Bias.left_center
    credibility: Credibility = Credibility.high

    def setup(self, soup: Soup):
        for a in soup.find_all('a', class_='topic-title'):
            href = self.url + a.get('href')[1:]
            title = a.text.strip()
            self.downstream.append((href, title))