import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class FoxBusiness(Scraper):
    url: str = 'https://www.foxbusiness.com/'
    agency: str = "Fox Business"
    bias: Bias = Bias.right_center
    credibility: Credibility = Credibility.mixed

    def setup(self, soup: Soup):
        for item in soup.find('div', {'class': 'page'}).find_all(
                'a', {'href': re.compile(r'//www.foxbusiness.com/[a-z-]+/[a-z-]+$')}):
            if 'category' in item['href']:
                continue
            if '/lifestyle/' in item['href']:
                continue
            href = item['href']
            if href.startswith('//'):
                href = f'https:{href}'
            if not item.text.strip():
                continue
            self.downstream.append((href, item))
