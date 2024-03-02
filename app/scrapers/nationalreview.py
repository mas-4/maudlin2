from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NationalReview(SeleniumScraper):
    bias = Bias.right
    credibility = Credibility.mostly_factual
    url: str = 'https://www.nationalreview.com'
    agency: str = "National Review"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-testid': 'dynamic-link'}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

