import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Axios(Scraper):
    # todo: requires chrome headless and selenium
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.axios.com'
    agency: str = "Axios"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
