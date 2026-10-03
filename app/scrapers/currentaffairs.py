import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CurrentAffairs(Scraper):
    headers = Constants.Headers.firefox
    url: str = 'https://www.currentaffairs.org'
    agency: str = "Current Affairs"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/news/(?!tag/)[\w-]+')}):
            title = a.text.strip()
            if title:
                self.downstream.append((a['href'], a))
