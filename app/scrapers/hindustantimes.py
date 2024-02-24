from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger
from app.scraper import SeleniumScraper

logger = get_logger(__name__)


class HindustanTimes(SeleniumScraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.hindustantimes.com'
    agency: str = "Hindustan Times"
    country: Country = Country.in_

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-articleid': True}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

