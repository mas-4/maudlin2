

from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, Constants, get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class NewsNation(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.newsnationnow.com/'
    agency: str = "News Nation"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-link-label': True}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

