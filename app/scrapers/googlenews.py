import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GoogleNews(Scraper):
    bias = Bias.left_center  # really? Isn't it an algorithm?
    credibility = Credibility.mostly_factual
    url: str = 'https://news.google.com/home?hl=en-US&gl=US&ceid=US:en'
    agency: str = "Google News"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'\./articles/')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
