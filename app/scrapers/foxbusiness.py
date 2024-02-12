import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class FoxBusiness(Scraper):
    url: str = 'https://www.foxbusiness.com/'
    agency: str = "Fox Business"
    bias: Bias = Bias.right_center
    credibility: Credibility = Credibility.mixed
    strip: list[str] = ["Fox Business"]
    parser: str = 'lxml'

    def setup(self, soup: Soup):
        for item in soup.find('div', {'class': 'page'}).find_all(
                'a', {'href': re.compile(r'//www.foxbusiness.com/[a-z-]+/[a-z-]+$')}):
            if 'category' in item['href']:
                continue
            if '/lifestyle/' in item['href']:
                continue
            href = item['href']
            if href.startswith('//'):
                href = f'https:{href}'
            if not (title := item.text.strip()):
                continue
            self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('div', {'class': 'article-body'}).find_all('p'):
            if a := p.find('a'):
                if a.text.strip() == p.text.strip():
                    continue
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })
