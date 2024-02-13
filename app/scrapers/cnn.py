from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

logger = get_logger(__name__)


class CNN(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://lite.cnn.com/'
    agency: str = "CNN"

    def setup(self, soup: Soup):
        for li in soup.find_all('li', class_='card--lite'):
            a = li.find('a')
            href = self.url + a.get('href')[1:]  # /path/ can't have the /
            title = a.text.strip()
            self.downstream.append((href, title))
