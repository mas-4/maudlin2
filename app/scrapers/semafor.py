import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility


class Semafor(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.semafor.com'
    agency: str = "Semafor"

    def setup(self, soup: Soup):
        for a in soup.find('div', {'class': re.compile('styles_grid')}).find_all(
                'a', {'href': re.compile(".*/article/.*")}):
            href = self.url + a['href']
            title = a.find('h2')
            self.downstream.append((href, title))
