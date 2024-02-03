from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

logger = get_logger(__name__)


class NPR(Scraper):
    url: str = 'https://text.npr.org/'
    agency: str = "NPR"
    bias: Bias = Bias.left_center
    credibility: Credibility = Credibility.high
    strip: list[str] = ['NPR News', 'NPR', 'By .*$', ">"]

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
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })