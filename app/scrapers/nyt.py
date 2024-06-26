import re

from bs4 import BeautifulSoup as Soup

from app.scraper import Scraper
from app.utils.constants import Bias, Credibility
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NYT(Scraper):
    bias = Bias.left_center
    credibility = Credibility.high
    url: str = 'https://www.nytimes.com/'
    agency: str = "New York Times"

    def setup(self, soup: Soup):
        ignore = 'podcasts', 'crosswords',
        for a in soup.find_all(
                'a',
                {
                    'href': re.compile(r'https://www\.nytimes\.com/\d{4}/\d{2}/\d{2}'),
                    'aria-hidden': "false"
                }
        ):
            href = a['href']
            section = re.search(r'https://www.nytimes\.com/\d{4}/\d{2}/\d{2}/(\w+)', href).group(1)
            if section in ignore:
                continue
            try:
                title = a.find('p', {'class': 'indicate-hover'})
            except:  # noqa exc
                logger.exception(a)
                continue
            self.downstream.append((href, title))
