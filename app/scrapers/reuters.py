import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class Reuters(Scraper):
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
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

