from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class TampaBayTimes(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.tampabay.com'
    agency: str = "Tampa Bay Times"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

