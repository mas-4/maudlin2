from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils import Bias, Credibility, Constants, get_logger

logger = get_logger(__name__)


class IndependentJournalReview(Scraper):
    bias = Bias.right
    credibility = Credibility.mostly_factual
    url: str = 'https://ijr.com/'
    agency: str = "Independent Journal Review"
    headers = {'User-Agent': Constants.Headers.UserAgents.maudlin}

    def setup(self, soup: Soup):
        for a in soup.find('div', class_='jeg_content').find_all('a'):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
