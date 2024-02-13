import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NBC(Scraper):
    url: str = 'https://www.nbcnews.com'
    agency: str = "NBC News"
    bias: Bias = Bias.left_center
    credibility: Credibility = Credibility.high

    def setup(self, soup: Soup):
        for a in soup.find_all('a',
                               {'href': re.compile(r"https://www.nbcnews.com/[a-z-]+/[a-z-]+/[a-z-]+")}):
            if 'live-updates' in a['href']:
                continue
            if '/select/' in a['href']:
                continue
            href = a['href']
            title = a.text.strip()
            self.downstream.append((href, title))
