import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class France24(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.france24.com/en'
    agency: str = "France24"
    country: Country = Country.fr
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/en/.*/\d{8}-.*')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
