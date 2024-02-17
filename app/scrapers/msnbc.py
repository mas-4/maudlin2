import re
import nltk

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class MSNBC(Scraper):
    bias = Bias.left
    credibility = Credibility.mixed
    url: str = 'https://www.msnbc.com'
    agency: str = "MSNBC"
    stopwords = ["AD Choices", "AP", "Getty Images", ";", ]

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'\d+$')}):
            href = a['href']
            title = a.text.strip()
            if '/' in title:
                continue
            # basically if it's nothing but personal nouns ignore it
            if not list(filter(lambda x: x[1] != 'NNP', nltk.pos_tag(nltk.word_tokenize(title)))):
                continue
            self.downstream.append((href, title))

