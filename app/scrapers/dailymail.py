import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country
from app.utils.logger import get_logger

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
