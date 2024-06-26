from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

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
                self.downstream.append((href, a))
