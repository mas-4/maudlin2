from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class CNN(Scraper):
    def __init__(self):
        self.url = 'https://lite.cnn.com/'
        self.agency = "CNN"
        super().__init__()

    def setup(self, soup: Soup):
        for li in soup.find_all('li', class_='card--lite'):
            a = li.find('a')
            href = self.url + a.get('href')[1:]  # /path/ can't have the /
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


