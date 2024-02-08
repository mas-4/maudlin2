import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Breitbart(Scraper):
    bias = Bias.extreme_right
    credibility = Credibility.mixed
    url: str = 'https://www.breitbart.com/'
    agency: str = "Breitbart"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        article = page.find('article')
        article.footer.decompose()
        for p in article.find_all(['p', 'ul', 'blockquote']):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


