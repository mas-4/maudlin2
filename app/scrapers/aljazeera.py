from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.constants import Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AlJazeera(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.aljazeera.com'
    agency: str = "Al Jazeera"
    country = Country.qa

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            if not href.startswith('http'):
                href = self.url + href
            title = a.text.strip().replace('\xad', '')
            if title:
                self.downstream.append((href, a))
