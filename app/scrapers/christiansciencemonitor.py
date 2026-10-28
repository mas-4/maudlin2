import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper, without
from app.utils import get_logger

logger = get_logger(__name__)

# A story's photo is a link of its own with the credit inside it ("Scott Peterson/Getty Images/The Christian Science
# Monitor"): kept as headlines until Oct 28
PHOTO_PARTS = '[data-field="credit"]'


class ChristianScienceMonitor(Scraper):
    url: str = 'https://www.csmonitor.com/'
    agency: str = "The Christian Science Monitor"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{4}/')}):
            try:
                self.downstream.append((a['href'], without(a, PHOTO_PARTS)))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
