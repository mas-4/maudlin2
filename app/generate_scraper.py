import os
import sys
import re

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
    class_name = site_name.replace(' ', '')
    file_name = site_name.lower().replace(' ', '') + '.py'
    generate_scraper(site_name, url, class_name, file_name)
    register_scraper(class_name, file_name)


def register_scraper(class_name, file_name):
    registry_path = os.path.join(Constants.Paths.ROOT, 'app', 'registry.py')
    with open(registry_path, 'rt') as f:
        registry = f.read()
    registry = f"from app.scrapers.{file_name.replace('.py', '')} import {class_name}\n" + registry
    registry = re.sub(r"Scrapers = \[", f"Scrapers = [\n    {class_name},", registry)
    with open(registry_path, 'wt') as f:
        f.write(registry)



def generate_scraper(site_name, url, class_name, file_name):
    print(f"Generating scraper for {site_name} at {url}")
    path = os.path.join(Constants.Paths.ROOT, 'app', 'scrapers', file_name)
    with open(path, "wt") as f:
        f.write(template.format(cls=class_name, url=url, site_name=site_name))
    print(f"Generated scraper for {site_name} at {url}")


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])