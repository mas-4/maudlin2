import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class TorontoSun(Scraper):
    bias = Bias.right
    credibility = Credibility.mostly_factual
    url: str = 'https://torontosun.com/'
    agency: str = "Toronto Sun"
    country = Country.ca
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'^/(news|opinion)/.*')}):
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
