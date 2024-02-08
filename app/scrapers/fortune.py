from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Fortune(Scraper):
    bias = Bias.right_center
    credibility = Credibility.high
    url: str = 'https://fortune.com'
    agency: str = "Fortune"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        article = page.find('div', {'id': 'article-content'})
        for p in article.find_all(['p', 'li', 'blockquote']):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


