import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class DailyMail(Scraper):
    bias = Bias.right
    credibility = Credibility.low
    url: str = 'https://www.dailymail.co.uk'
    agency: str = "Daily Mail"
    strip: list[str] = []
    country = Country.gb


    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/article-\d+/')}):
            if a['href'].startswith('https:'):
                continue
            href = re.sub('#.*', '', 'https://dailymail.co.uk' + a['href'])
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find('div', {'class': 'alpha'}).find_all('p', {'class': 'mol-para-with-font'}):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


