from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class BusinessInsider(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.businessinsider.com'
    agency: str = "Business Insider"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-analytics-product-module': 'hp_tout_clicks'}):
            href = a['href']
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
