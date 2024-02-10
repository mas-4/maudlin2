import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class IndiaTimes(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://www.indiatimes.com'
    agency: str = "India Times"
    strip: list[str] = []
    country = Country.in_


    def setup(self, soup: Soup):
        for a in soup.find_all('a', { 'href': re.compile(r"-\d+\.html")}):
            if (href := a['href']).startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


