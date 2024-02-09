import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Jacobin(Scraper):
    bias = Bias.extreme_left
    credibility = Credibility.high
    url: str = 'https://jacobin.com'
    agency: str = "Jacobin"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/')}):
            href = a['href']
            if not href.startswith('https://'):  # catalyst-journal.com links? what are they
                href = self.url + href
            else:
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find_all('section', {'id': re.compile('ch-\d{1,2}')}):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


