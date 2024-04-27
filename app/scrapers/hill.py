import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Hill(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.mostly_factual
    url: str = 'https://thehill.com/'
    agency: str = "The Hill"
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/\d+-.*')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
