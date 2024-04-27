from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class PoliticalWire(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://politicalwire.com/'
    agency: str = "Political Wire"
    headers: dict = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            title = a.text.strip()
            if "Quote of the Day" in title:
                continue
            self.downstream.append((href, a))
