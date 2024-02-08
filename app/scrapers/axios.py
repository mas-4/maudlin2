import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Axios(Scraper):
    # todo: requires chrome headless and selenium
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.axios.com'
    agency: str = "Axios"
    strip: list[str] = []


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('div', {'class': re.compile('DraftjsBlocks')}
                           ).find_all(['p', 'ul']):
            p.select('strong')
            p.extract()
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


