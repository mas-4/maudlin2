import re

import nltk
from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

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
