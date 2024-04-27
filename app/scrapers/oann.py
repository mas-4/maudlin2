import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class OneAmericaNewsNetwork(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.low
    url: str = 'https://www.oann.com'
    agency: str = "One America News Network"
    country: str = Country.us

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile("^https://www.oann.com/.+/.+")}):
            href = a['href']
            if 'category' in href:
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
