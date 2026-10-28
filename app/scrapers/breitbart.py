import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Breitbart(Scraper):
    url: str = 'https://www.breitbart.com/'
    agency: str = "Breitbart"
    # Its late-night posts reach the homepage low down or the next morning, so a fifth of its articles were first seen
    # a day after their date (Oct 28); the feed lists each as it goes up. First sightings only: app/feed_sightings.py
    side_feed: str = 'https://feeds.feedburner.com/breitbart'

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/\d{2}/')}):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, a))
