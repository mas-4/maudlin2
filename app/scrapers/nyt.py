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
    headline_only = True
    strip = ["New York Times", "NYT", "The New York Times", "NY Times", "News Digital", "News", "New"]


    def setup(self, soup: Soup):
        ignore = 'podcasts', 'crosswords',
        for a in soup.find_all(
                'a',
                {
                    'href': re.compile(r'https://www\.nytimes\.com/\d{4}/\d{2}/\d{2}'),
                    'aria-hidden': "false"
                }
        ):
            href = a['href']
            section = re.search(r'https://www.nytimes\.com/\d{4}/\d{2}/\d{2}/(\w+)', href).group(1)
            if section in ignore:
                continue
            try:
                title = a.find('p', {'class': 'indicate-hover'}).text.strip()
            except:
                logger.exception(a)
                raise
            self.downstream.append((href, title))

    def consume(self, page: Soup, href: str, title: str):
        pass  # headline only
