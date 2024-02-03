import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NBC(Scraper):
    url: str = 'https://www.nbcnews.com'
    agency: str = "NBC News"
    bias: Bias = Bias.left_center
    credibility: Credibility = Credibility.high
    strip: list[str] = []

    def setup(self, soup: Soup):
        for a in soup.find_all('a',
                               {'href': re.compile(r"https://www.nbcnews.com/[a-z-]+/[a-z-]+/[a-z-]+")}):
            if 'live-updates' in a['href']:
                continue
            href = a['href']
            title = a.text.strip()
            self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        title = page.find("h1", class_="article-hero-headline__htag").text.strip()
        for p in page.find("div", class_="article-body__content").find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })
