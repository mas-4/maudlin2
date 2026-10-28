from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper, without
from app.utils import Constants, get_logger

logger = get_logger(__name__)

# Townhall Media's cards (Townhall, Red State) put a section label and the author's name inside the headline's link
# ("Polling  This Gallup Poll Shows…  Amy Curtis"): about half their headlines carried a byline until Oct 28
CARD_EXTRAS = '.th-ts-eye, .th-ts-by, .th-brk-eye, .th-brk-by'


class Townhall(Scraper):
    url: str = 'https://townhall.com'
    agency: str = "Townhall"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                self.downstream.append((a['href'], without(a, CARD_EXTRAS)))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
