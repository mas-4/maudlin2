import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class NYT(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.nytimes.com/'
    agency: str = "New York Times"
    # Leaving this scraper disabled for now because honestly not sure about the legality here.
    headers: dict[str, str] = {"User-Agent": '"User-Agent: Googlebot/2.1 (+http://www.google.com/bot.html)"'}

    def setup(self, soup: Soup):
        ignore = 'podcasts', 'crosswords',
        for a in soup.find_all('a', {'href': re.compile(r'https://www\.nytimes\.com/\d{4}/\d{2}/\d{2}')}):
            href = a['href']
            section = re.search(r'https://www.nytimes\.com/\d{4}/\d{2}/\d{2}/(\w+)', href).group(1)
            if section in ignore:
                continue
            title = a.text.strip()
            self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find_all('p', {'class': 'css-at9mc1 evys1bk0'}):
            story.append(p.text.strip())
        self.results.append({
            'body': ' '.join(story),
            'title': title,
            'url': href
        })


