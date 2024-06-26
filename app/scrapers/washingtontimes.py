import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, Constants, get_logger

logger = get_logger(__name__)


class WashingtonTimes(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.washingtontimes.com/'
    agency: str = "The Washington Times"
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/news/')}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
