import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class GlobalTimes(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.globaltimes.cn/'
    agency: str = "Global Times"
    strip: list[str] = []
    country = Country.cn


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile('/page/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = page.find('div', {'class': 'article_right'}).text.strip()
        self.results.append({
            'body': story,
            'title': title,
            'url': href
        })


