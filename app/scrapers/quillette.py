from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Quillette(Scraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://quillette.com/'
    agency: str = "Quillette"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
