from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BBC(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.bbc.com'
    agency: str = "BBC"
    country = Country.gb

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-testid': 'internal-link'}):
            href = a['href']
            if 'cloud.email.bbc' in href:
                continue
            if not href.startswith('http'):
                href = self.url + href
            if not (title := a.find('h2', {'data-testid': 'card-headline'})):
                continue
            if not (title := title.text.strip()):
                continue
            self.downstream.append((href, title))
