import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NBC(Scraper):
    url: str = 'https://www.nbcnews.com'
    agency: str = "NBC News"
    bias: Bias = Bias.left_center
    credibility: Credibility = Credibility.high

    def setup(self, soup: Soup):
        for a in soup.find_all('a',
                               {'href': re.compile(r"https://www.nbcnews.com/[a-z-]+/[a-z-]+/[a-z-]+")}):
            if '/select/' in a['href']:
                continue
            href = a['href']
            title = a.text.strip()
            self.downstream.append((href, title))
