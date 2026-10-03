import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

logger = get_logger(__name__)

TIMESTAMP = re.compile(r'^\d{1,2}:\d{2}\s+')


class TimesofIndia(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://timesofindia.indiatimes.com/us'
    agency: str = "The Times of India"
    country = Country.in_

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/\d+\.cms')}):
            # Each link wraps the headline with a summary paragraph and labels ("Live", "World", a "15:06" timestamp,
            # a slideshow count), and the class names are machine generated. The headline is the shortest piece of
            # text of four words or more: the wrappers around it are longer, the labels shorter.
            for summary in a.find_all('p'):
                summary.decompose()
            elements = [a, *a.find_all(True)]
            # Sometimes the headline is bare text beside a label element, so each element's own text counts too
            texts = [el.get_text(' ', strip=True) for el in elements] + \
                    [' '.join(t.strip() for t in el.find_all(string=True, recursive=False)) for el in elements]
            texts = [TIMESTAMP.sub('', t) for t in texts]
            candidates = [t for t in texts if len(t.split()) >= 4]
            if candidates:
                self.downstream.append((a['href'], min(candidates, key=len)))
