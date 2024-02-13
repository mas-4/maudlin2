import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class DailyMail(Scraper):
    bias = Bias.right
    credibility = Credibility.low
    url: str = 'https://www.dailymail.co.uk'
    agency: str = "Daily Mail"
    country = Country.gb
    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': re.compile(r'/article-\d+/')}):
            if a['href'].startswith('https:'):
                continue
            href = re.sub('#.*', '', 'https://dailymail.co.uk' + a['href'])
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))
