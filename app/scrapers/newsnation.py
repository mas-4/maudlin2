from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, get_logger

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
