import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class SkyNews(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://news.sky.com'
    agency: str = "Sky News"
    country: str = Country.gb

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*-\d+$')}):
            href = a['href']
            title = a.text.strip()
            self.downstream.append((href, title))

