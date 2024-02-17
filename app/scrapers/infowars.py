import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class InfoWars(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.very_low
    url: str = 'https://www.infowars.com/'
    agency: str = "Info Wars"
    headers = {'User-Agent': Constants.Headers.UserAgents.desktop_google_bot}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/posts/.*')}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

