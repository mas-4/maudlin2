from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.constants import Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

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
                self.downstream.append((href, title))
