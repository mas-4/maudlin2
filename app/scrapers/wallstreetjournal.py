import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class WallStreetJournal(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.wsj.com/'
    agency: str = "The Wall Street Journal"
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for art in soup.find_all('article'):
            try:
                a = art.find('a')
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

