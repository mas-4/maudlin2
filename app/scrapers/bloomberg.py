import re
import time

from bs4 import BeautifulSoup as Soup

from app.scraper import FeedScraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Bloomberg(FeedScraper):
    """Bloomberg's own section feeds. Its front page answers every request with a captcha ("Are you a robot?") since
    Oct 11, 20:04, and we don't get around bot checks; the official feeds answer (Oct 12, the person: pause it "unless"
    an official feed exists). Politics, markets and economics, the front page's main sections, a few seconds apart;
    articles only (the feeds carry videos too), tagged as the front page tagged them so the articles already kept
    match."""
    url: str = 'https://www.bloomberg.com'
    agency: str = "Bloomberg"
    feed: str = 'https://www.bloomberg.com/feeds/politics/news.rss'
    feeds: tuple = ('https://www.bloomberg.com/feeds/politics/news.rss',
                    'https://www.bloomberg.com/feeds/markets/news.rss',
                    'https://www.bloomberg.com/feeds/economics/news.rss')
    between: float = 10  # seconds between the feeds: polite, as one site
    TAG = '?srnd=homepage-americas'  # what the front page's links carried, so a feed's link is the same article

    def run_setup(self):
        seen = set()
        for n, feed in enumerate(self.feeds):
            if n:
                time.sleep(self.between)
            page = self.get_page(feed)
            if page:
                self.setup(page, seen)

    def setup(self, soup: Soup, seen: set | None = None):
        seen = seen if seen is not None else set()
        for item in soup.find_all('item'):
            title, link = item.find('title'), item.find('link')
            if title is None or link is None:
                continue
            href = link.get_text(strip=True).split('?')[0]
            text = title.get_text(strip=True)
            if text and re.search(r'/news/articles/', href) and href not in seen:
                seen.add(href)
                self.downstream.append((href + self.TAG, text))
