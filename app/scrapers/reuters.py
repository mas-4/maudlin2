import re

from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Reuters(SeleniumScraper):
    bias = Bias.unbiased
    credibility = Credibility.very_high
    url: str = 'https://www.reuters.com/'
    agency: str = "Reuters"
    country = Country.gb
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'-\d{4}-\d{2}-\d{2}/?')}):
            try:
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
