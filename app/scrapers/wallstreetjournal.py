from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Constants
from app.utils.logger import get_logger
from app.scraper import SeleniumScraper

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
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

