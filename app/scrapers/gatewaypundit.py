

from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, Constants, get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class GatewayPundit(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.very_low
    url: str = 'https://www.thegatewaypundit.com/'
    agency: str = "The Gateway Pundit"
    headers = {
        "User-Agent": Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_MONTH}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

