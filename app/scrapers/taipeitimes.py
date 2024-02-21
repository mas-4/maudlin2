from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class TaipeiTimes(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.taipeitimes.com/'
    agency: str = "Taipei Times"
    country: str = Country.tw

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            href = a['href']
            title = a.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
            if title:
                title = title.text.strip()
            elif a.text:
                title = a.text.strip()
            else:
                continue
            self.downstream.append((href, title))

