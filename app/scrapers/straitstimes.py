from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class StraitsTimes(SeleniumScraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.straitstimes.com/global'
    agency: str = "The Straits Times"
    country = Country.sg
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'class': 'stretched-link'}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
