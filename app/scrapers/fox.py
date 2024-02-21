import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Fox(Scraper):
    url: str = 'https://www.foxnews.com/'
    agency: str = "Fox News"
    bias: Bias = Bias.right
    credibility: Credibility = Credibility.mixed

    def setup(self, soup: Soup):
        for item in soup.find('div', {'class': 'page'}).find_all(
                'a', {'href': re.compile(r'//www.foxnews.com/[a-z-]+/[a-z-]+$')}):
            if 'category' in item['href']:
                continue
            if '/lifestyle/' in item['href']:
                continue
            href = item['href']
            if href.startswith('//'):
                href = f'https:{href}'
            if not (title := item.text.strip()):
                continue
            self.downstream.append((href, title))
