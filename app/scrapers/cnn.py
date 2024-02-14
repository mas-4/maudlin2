from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

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
            title = a.text.strip()
            self.downstream.append((href, title))
