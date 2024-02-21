from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class NDTV(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.ndtv.com/'
    agency: str = "NDTV"
    country = Country.in_

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': 'item-title'}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

