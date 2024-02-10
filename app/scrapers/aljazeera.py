from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Constants
from app.constants import Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class AlJazeera(Scraper):
    bias = Bias.left_center
    credibility = Credibility.mixed
    url: str = 'https://www.aljazeera.com'
    agency: str = "Al Jazeera"
    strip: list[str] = []
    country = Country.qa


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.DATE_URL}):
            href = a['href']
            if not href.startswith('http'):
                href = self.url + href
            title = a.text.strip().replace('\xad', '')
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('main').find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


