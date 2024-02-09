from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class BusinessInsider(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mostly_factual
    url: str = 'https://www.businessinsider.com'
    agency: str = "Business Insider"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'data-analytics-product-module': 'hp_tout_clicks'}):
            href = a['href']
            if href.startswith('//'):
                href = 'https:' + href
            elif href.startswith('/'):
                href = self.url + href
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('div', {'data-component-type': 'content-lock'}).find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


