import re

import requests
from bs4 import BeautifulSoup as Soup, BeautifulSoup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class DailyKos(Scraper):
    bias = Bias.extreme_left
    credibility = Credibility.mixed
    url: str = 'https://www.dailykos.com'
    agency: str = "The Daily Kos"
    strip: list[str] = ["Daily Kos"]

    def get_page(self, url):
        if url == self.url:
            return BeautifulSoup(requests.get(url).text, 'lxml')
        code = re.search(r'/\d{4}/\d{1,2}/\d{1,2}/(\d+)/', url).group(1)
        logger.debug("Daily Kos: Found code %s", code)
        return requests.get(f'https://www.dailykos.com/api/v1/story_content/{code}').json()

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{1,2}/\d{1,2}/')}):
            h3 = a.find('h3')
            if not h3:
                continue
            title = h3.text.strip()
            href = a['href']
            if not href.startswith('http'):
                href = f'{self.url}{href}'
            self.downstream.append((href, title))

    def consume(self, page: dict, href: str, title: str):
        story = []
        story.extend([v['name'] for v in page['tags']])
        soup = BeautifulSoup(
            page['story_text']['story_text_before_ad'] + page['story_text']['story_text_after_ad'],
            'lxml'
        )
        for p in soup.find_all('p'):
            story.append(p.text.strip())

        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })
