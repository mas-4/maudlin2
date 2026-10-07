from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CBS(Scraper):
    url: str = 'https://www.cbsnews.com'
    agency: str = "CBS News"

    def setup(self, soup: Soup):
        for art in soup.find_all('article'):
            a = art.find('a')
            if not a:
                continue
            href = a['href']
            # the link wraps the whole card; keep the headline, not the summary line and timestamp under it
            hed = a.find(class_='item__hed') or a
            if hed.text.strip():
                self.downstream.append((href, hed))
