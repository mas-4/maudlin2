from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class CBS(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.cbsnews.com'
    agency: str = "CBS News"

    def setup(self, soup: Soup):
        for art in soup.find_all('article'):
            a = art.find('a')
            if not a:
                continue
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
