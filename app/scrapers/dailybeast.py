from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

logger = get_logger(__name__)


class DailyBeast(Scraper):
    # todo chrome headless selenium support
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.thedailybeast.com/'
    agency: str = "The Daily Beast"
    strip: list[str] = []
    def setup(self, soup: Soup):
        pass
