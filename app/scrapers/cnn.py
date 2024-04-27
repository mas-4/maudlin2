from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CNN(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://www.cnn.com'
    agency: str = "CNN"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-link-type': 'article'}):
            href = self.url + a['href']
            if 'cnn-underscored' in href:
                continue
            if '/wbd/' in href:
                continue
            self.downstream.append((href, a))
