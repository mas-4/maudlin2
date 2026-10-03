import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Slate(Scraper):
    bias = Bias.left
    credibility = Credibility.mostly_factual
    url: str = 'https://slate.com'
    agency: str = "Slate"

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d{4}/\d{2}/')}):
            # Cards come in several layouts (story-card, story-teaser, ...); each has a *__headline element, with the
            # author and a "Slate Plus" badge beside it rather than in it
            headline = a.find(class_=re.compile(r'__headline$'))
            if headline is None:
                continue
            # Slate A/B tests headlines: the card holds every variant and a script reveals one at random. The
            # <noscript> copy is the default one, shown to readers without javascript.
            default = headline.find('noscript') or headline.find(attrs={'data-promoline-variant': True}) or headline
            self.downstream.append((a['href'], default.get_text(' ', strip=True)))
