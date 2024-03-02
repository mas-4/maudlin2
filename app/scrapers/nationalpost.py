import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NationalPost(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://nationalpost.com'
    agency: str = "National Post"
    country = Country.ca
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for span in soup.find_all('span', {'class': re.compile('card__headline-clamp')}):
            a = span.find_parent('a')
            href = a['href']
            if href.startswith('/'):
                href = self.url + href
            title = span.text.strip()
            if title:
                self.downstream.append((href, title))
