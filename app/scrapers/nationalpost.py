import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NationalPost(Scraper):
    url: str = 'https://nationalpost.com'
    agency: str = "National Post"
    country = Country.ca
    headers = {
        'User-Agent': Constants.Headers.UserAgents.maudlin
    }

    def setup(self, soup: Soup):
        """Every story link carries Postmedia's analytics, target_type "article" (Oct 31: the card__headline-clamp
        spans went in a redesign, and the scraper found nothing)"""
        for a in soup.find_all('a', {'data-analytics-properties': re.compile(r'"target_type"\s*:\s*"article"')}):
            if 'postmedia-image__link' in a.get('class', []):
                continue  # the picture's link to the same story, no words
            title = a.get_text(' ', strip=True)
            if not title or "horoscope" in title.lower():
                continue
            self.downstream.append((self.clean_href(a['href']), a))
