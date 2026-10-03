import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class MilitaryCom(Scraper):
    headers = Constants.Headers.firefox
    url: str = 'https://www.military.com'
    agency: str = "Military.com"

    def setup(self, soup: Soup):
        # articles live at a top level slug like /dod-increases-hazard-pays-for-first-time
        for a in soup.find_all('a', {'href': re.compile(r'^(https://www\.military\.com)?/[a-z0-9]+(-[a-z0-9]+){3,}/?$')}):
            title = a.text.strip()
            if title:
                self.downstream.append((a['href'], a))
