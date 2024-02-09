import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class HuffPost(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.huffpost.com/'
    agency: str = "HuffPost"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/entry/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('section', {'class': 'js-entry-content'}).find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


