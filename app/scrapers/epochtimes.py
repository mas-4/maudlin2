import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class EpochTimes(Scraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://www.theepochtimes.com'
    agency: str = "The Epoch Times"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-title': "true"}):
            try:
                href = a['href']
                title = a.find(['h1', 'h2', 'h3', 'h4'])
                if title:
                    title = title.text.strip()
                else:
                    title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

