from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class DailyWire(Scraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://www.dailywire.com/'
    agency: str = "The Daily Wire"

    def setup(self, soup: Soup):
        for art in soup.find_all('article'):
            try:
                a = art.find('a')
                href = a['href']
                title = a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']).text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

