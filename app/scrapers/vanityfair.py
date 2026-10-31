import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class VanityFair(Scraper):
    url: str = 'https://www.vanityfair.com/'
    agency: str = "Vanity Fair"

    def setup(self, soup: Soup):
        """Condé Nast's headline links, by class prefix: the suffix is a generated hash (Oct 31: the recirc-river
        links went and the scraper found nothing)"""
        for a in soup.find_all('a', {'class': re.compile(r'^(HeadlineLink|SummaryItemHedLink)-')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
