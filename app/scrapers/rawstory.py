from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class RawStory(Scraper):
    bias = Bias.left
    credibility = Credibility.high
    url: str = 'https://www.rawstory.com'
    agency: str = "Raw Story"
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'aria-label': True}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
