from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ChicagoTribune(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://www.chicagotribune.com/'
    agency: str = "Chicago Tribune"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'title': True}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
