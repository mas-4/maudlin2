import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PBSNewsHour(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.pbs.org/newshour/'
    agency: str = "PBS NewsHour"

    def setup(self, soup: Soup):
        for a in soup.find_all(
                'a',
                {'class': re.compile(r'title')}
        ):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
