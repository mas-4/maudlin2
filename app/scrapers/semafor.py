import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility
from app.scrapers.scraper import Scraper


class Semafor(Scraper):
    bias = Bias.center
    credibility = Credibility.high
    url: str = 'https://www.semafor.com'
    agency: str = "Semafor"
    strip: list[str] = [
        "Sign up for Semafor Principals",
        "What the White House is reading",
        "Read it now",
        "Sign up for.*\. Read it now.",
        "In this article:",
    ]

    def setup(self, soup: Soup):
        for a in soup.find('div', {'class': re.compile('styles_grid')}).find_all(
                'a', { 'href': re.compile(".*/article/.*")}):
            href = self.url + a['href']
            title = a.find('h2').text.strip()
            self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        story = []
        for p in page.find_all('p'):
            story.append(p.text.strip())
        self.results.append({
            'body': '\n'.join(story),
            'title': title,
            'url': href
        })


