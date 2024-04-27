from datetime import datetime as dt

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility, Country, Constants
from app.utils.logger import get_logger

logger = get_logger(__name__)


class JapanTimes(Scraper):
    bias = Bias.unbiased
    credibility = Credibility.high
    url: str = 'https://www.japantimes.co.jp/'
    agency: str = "The Japan Times"
    country = Country.jp

    def setup(self, soup: Soup):
        for a in soup.find_all('a', {'href': Constants.Patterns.SLASH_DATE}):
            try:
                href = a['href']
                if href.strip() == "https://www.japantimes.co.jp/archive/" + dt.now().strftime("%Y/%m/%d/"):
                    continue  # this is just a calendar
                self.downstream.append((href, a))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue
