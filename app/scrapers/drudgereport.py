from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class DrudgeReport(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.drudgereport.com/'
    agency: str = "Drudge Report"

    def setup(self, soup: Soup):
        # Drudge has a lot of non story links, but tbh who cares if they get added
        # I'm not going to filter them out
        self.downstream.extend([(a['href'], a.text.strip()) for a in soup.find_all('a', {'href': True})])
