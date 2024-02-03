from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

logger = get_logger(__name__)


class CNN(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://lite.cnn.com/'
    agency: str = "CNN"
    strip: list[str] = ['CNN', 'See Full Web Article', 'Updated:.*$', 'Source:.*$', 'By .*,$', "Source:"]


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
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


