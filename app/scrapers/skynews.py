import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class SkyNews(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://news.sky.com'
    agency: str = "Sky News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*-\d+$')}):
            href = a['href']
            title = a.text.strip()
            self.downstream.append((href, title))

