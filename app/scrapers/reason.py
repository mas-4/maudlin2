from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Reason(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://reason.com'
    agency: str = "Reason"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
