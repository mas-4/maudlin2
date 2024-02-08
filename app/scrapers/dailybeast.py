from bs4 import BeautifulSoup as Soup

from app.logger import get_logger
from app.scrapers.scraper import Scraper
from app.constants import Bias, Credibility

logger = get_logger(__name__)


class DailyBeast(Scraper):
    # todo chrome headless selenium support
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.thedailybeast.com/'
    agency: str = "The Daily Beast"
    strip: list[str] = []


    def setup(self, soup: Soup):
        pass

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('article').find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


