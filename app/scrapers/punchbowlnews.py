import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class PunchbowlNews(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://punchbowl.news'
    agency: str = "Punchbowl News"
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/article/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

