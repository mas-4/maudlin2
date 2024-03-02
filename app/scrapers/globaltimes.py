import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GlobalTimes(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.globaltimes.cn/'
    agency: str = "Global Times"
    country = Country.cn

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/page/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
