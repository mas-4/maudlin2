

from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, Constants, get_logger
from app.scraper import SeleniumScraper

logger = get_logger(__name__)


class PostMillennial(SeleniumScraper):
    bias = Bias.right
    credibility = Credibility.mixed
    url: str = 'https://thepostmillennial.com/'
    agency: str = "The Post Millennial"

    def setup(self, soup: Soup):
        # decompose 'header'
        header = soup.find('header')
        if header:
            header.decompose()
        # decompose footer
        footer = soup.find('footer')
        if footer:
            footer.decompose()
        for a in soup.find_all('a', {'href': True}):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

