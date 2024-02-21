import re

from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility
from app.scraper import Scraper


class Semafor(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.semafor.com'
    agency: str = "Semafor"
    def setup(self, soup: Soup):
        for a in soup.find('div', {'class': re.compile('styles_grid')}).find_all(
                'a', { 'href': re.compile(".*/article/.*")}):
            href = self.url + a['href']
            title = a.find('h2').text.strip()
            self.downstream.append((href, title))
