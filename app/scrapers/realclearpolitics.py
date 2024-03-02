import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RealClearPolitics(SeleniumScraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.realclearpolitics.com'
    agency: str = "Real Clear Politics"
    headers = {
        'User-Agent': Constants.Headers.UserAgents.desktop_google_bot
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'onclick': re.compile(r'return ClickTracking.record_click')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
