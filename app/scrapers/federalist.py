from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Federalist(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.mixed
    url: str = 'https://thefederalist.com/'
    agency: str = "The Federalist"
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

