import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RadioFreeEuropeRadioLiberty(Scraper):
    url: str = 'https://www.rferl.org/'
    agency: str = "Radio Free Europe Radio Liberty"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/a/.*/\d+\.html')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
