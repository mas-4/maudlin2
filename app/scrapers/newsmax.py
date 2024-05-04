from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Newsmax(SeleniumScraper):
    bias = Bias.extreme_right
    credibility = Credibility.low
    url: str = 'https://www.newsmax.com'
    agency: str = "Newsmax"
    country: str = Country.us

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
