import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IndiaTimes(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.indiatimes.com'
    agency: str = "India Times"
    country = Country.in_

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r"-\d+\.html")}):
            if (href := a['href']).startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
