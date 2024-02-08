from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class CBS(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.cbsnews.com'
    agency: str = "CBS News"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for art in soup.find_all('article'):
            a = art.find('a')
            if not a:
                continue
            href = a['href']
            if '/video/' in href or '/live/' in href:
                continue
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        article = page.find('section', {'class': 'content__body'})
        aside = article.find('aside')
        if aside:
            aside.decompose()
        for p in article.find_all(['p', 'ul', 'blockquote']):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


