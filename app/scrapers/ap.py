import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class AP(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://apnews.com/'
    agency: str = "AP"
    strip: list[str] = ["Associated Press", "AP", "AP Photo"]


    def setup(self, soup: Soup):
        for a in soup.find('main', {'class': 'Page-oneColumn'}).find_all(
                'a', { 'href': re.compile(".*/article/.*")}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('bsp-story-page').find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


