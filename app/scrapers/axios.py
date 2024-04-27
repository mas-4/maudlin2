import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Axios(SeleniumScraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.axios.com'
    agency: str = "Axios"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            title = a.text.strip()
            if "Go deeper" in title:
                continue
            self.downstream.append((href, a))
