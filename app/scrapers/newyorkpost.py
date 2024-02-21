from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class NewYorkPost(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://nypost.com'
    agency: str = "New York Post"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

