import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class HuffPost(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.huffpost.com/'
    agency: str = "HuffPost"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/entry/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
