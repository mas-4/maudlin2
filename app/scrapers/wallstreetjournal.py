from bs4 import BeautifulSoup as Soup

from app.scraper import SeleniumScraper
from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class WallStreetJournal(SeleniumScraper):
    bias = Bias.right_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.wsj.com/'
    agency: str = "The Wall Street Journal"
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for art in soup.find_all('article'):
            try:
                a = art.find('a')
                href = a['href']
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")  # noqa not ref
                continue
