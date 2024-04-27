import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SouthChinaMorningPost(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.scmp.com'
    agency: str = "South China Morning Post"
    country: str = Country.cn

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/article/')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
