from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class BBC(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.bbc.com'
    agency: str = "BBC"
    strip: list[str] = []
    country = Country.gb


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-testid': 'internal-link'}):
            href = a['href']
            if not href.startswith('http'):
                href = self.url + href
            if title := a.find('h2', {'data-testid': 'card-headline'}):
                self.downstream.append((href, title.text.strip()))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find_all('section', {'data-component': 'text-block'}):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


