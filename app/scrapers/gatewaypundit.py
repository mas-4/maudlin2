from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper, without
from app.utils import Constants, get_logger

logger = get_logger(__name__)


class GatewayPundit(Scraper):
    url: str = 'https://www.thegatewaypundit.com/'
    agency: str = "The Gateway Pundit"
    headers = {
        "User-Agent": Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_MONTH}):
            try:
                # The trending list's view count sits inside the link ("86.3K views Translation Reveals…"): a byline
                # glued on, and a new "headline" every time the count moved
                self.downstream.append((a['href'], without(a, '[data-pa-f="views"], .pa-trending__views')))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
