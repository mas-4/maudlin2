import os
import sys
from app.constants import Constants

template = """import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country
from app.logger import get_logger
from app.scrapers.scraper import Scraper

logger = get_logger(__name__)


class {cls}(Scraper):
    bias = Bias.replace
    credibility = Credibility.replace
    url: str = '{url}'
    agency: str = "{site_name}"

    def setup(self, soup: Soup):
        for a in soup.find_all('a'):
            href = a['href']
            title = a.text.strip()
            if title:
                self.downstream.append((href, title))

"""

def main(site_name, url):
    print(f"Generating scraper for {site_name} at {url}")
    path = os.path.join(Constants.Paths.ROOT, 'app', 'scrapers', f"{site_name.lower().replace(' ', '')}.py")
    with open(path, "wt") as f:
        f.write(template.format(cls=site_name.replace(' ', ''), url=url, site_name=site_name))
    print(f"Generated scraper for {site_name} at {url}")

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])