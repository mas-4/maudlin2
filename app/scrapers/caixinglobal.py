import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CaixinGlobal(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.caixinglobal.com'
    agency: str = "Caixin Global"
    country = Country.cn

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'.*/\d{4}-\d{2}-\d{2}/.*')}):
            href = a['href']
            if href.startswith('//'):
                href = 'https:' + href
            href = re.sub(r'\n\?.*', '', href)
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
