import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class Fox(Scraper):
    url: str = 'https://www.foxnews.com/'
    agency: str = "Fox News"
    bias: Bias = Bias.right
    credibility: Credibility = Credibility.mixed
    strip: list[str] = [
        "This material may not be published, broadcast, rewritten,",
        "or redistributed. ©2024 FOX News Network, LLC. All rights reserved.",
        "Quotes displayed in real-time or delayed by at least 15 minutes",
        "Market data provided by",
        "Factset",
        "Powered and implemented by",
        "FactSet Digital Solutions",
        "Legal Statement. Mutual Fund and ETF data provided by",
        "Refinitiv Lipper"
        "Fox News Flash top headlines are here"
        "Check out what's clicking on Foxnews.com",
        "CLICK TO GET THE FOX NEWS APP",
        "CLICK HERE TO GET THE FOX NEWS APP",
        "You've successfully subscribed to this newsletter!",
        "Subscribed",
        "Get all the stories you need-to-know from the most powerful name in news delivered first thing every morning to your inbox"

    ]
    parser: str = 'lxml'

    def setup(self, soup: Soup):
        for item in soup.find('div', {'class': 'page'}).find_all(
                'a', {'href': re.compile(r'//www.foxnews.com/[a-z-]+/[a-z-]+$')}):
            if 'category' in item['href']:
                continue
            href = item['href']
            if href.startswith('//'):
                href = f'https:{href}'
            self.downstream.append((href, item.text.strip()))

    def consume(self, page: Soup, href: str, title: str):
        title = page.find('h1', class_='headline').text.strip()
        story = []
        for p in page.find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })
