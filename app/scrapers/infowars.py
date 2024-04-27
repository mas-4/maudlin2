import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class InfoWars(SeleniumScraper):
    bias = Bias.extreme_right
    credibility = Credibility.very_low
    url: str = 'https://www.infowars.com/'
    agency: str = "Info Wars"
    headers = {'User-Agent': Constants.Headers.UserAgents.desktop_google_bot}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/posts/.*')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
