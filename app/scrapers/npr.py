from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NPR(Scraper):
    def __init__(self):
        self.url = 'https://text.npr.org/'
        self.agency = "NPR"
        super().__init__()

    def setup(self, soup: Soup):
        for a in soup.find_all('a', class_='topic-title'):
            href = self.url + a.get('href')[1:]
            title = a.text.strip()
            self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('article').find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': ' '.join(story),
            'title': title,
            'url': href
        })