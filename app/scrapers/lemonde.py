import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)


class LeMonde(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.lemonde.fr/en'
    agency: str = "Le Monde"
    country: Country = Country.fr

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/article/')}):
            href = a['href']
            if title := a.find(['h1', 'h2', 'h3'], {'class': re.compile('article__title')}):
                if title.text.strip():
                    self.downstream.append((href, title))
