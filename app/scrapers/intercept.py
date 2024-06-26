from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Intercept(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://theintercept.com/'
    agency: str = "The Intercept"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                href = a['href']
                title = a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                if title:
                    a = title
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
