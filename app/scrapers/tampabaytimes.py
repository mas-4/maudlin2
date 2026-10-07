from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TampaBayTimes(Scraper):
    url: str = 'https://www.tampabay.com'
    agency: str = "Tampa Bay Times"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
