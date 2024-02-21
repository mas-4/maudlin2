from bs4 import BeautifulSoup as Soup

from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class AlArabiya(Scraper):
    bias = Bias.right_center
    credibility = Credibility.mixed
    url: str = 'https://english.alarabiya.net'
    agency: str = "Al Arabiya"
    country = Country.sa
    headers = {'User-Agent': Constants.Headers.UserAgents.desktop_google_bot}

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'title': True}):
            href = self.url + a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

