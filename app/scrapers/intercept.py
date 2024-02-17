import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Intercept(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://theintercept.com/'
    agency: str = "The Intercept"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            try:
                href = a['href']
                title = a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
                if title:
                    title = title.text.strip()
                else:
                    title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

