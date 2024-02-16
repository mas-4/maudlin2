import os
import re

from app.config import Config
from app.constants import Constants

template = """import re

from bs4 import BeautifulSoup as Soup

from app.constants import Bias, Credibility, Country, Constants
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
            try:
                href = a['href']
                title = a.text.strip()
                self.downstream.append((href, title))
            except Exception as e:
                logger.error(f"{self.agency}: Error parsing link: {e}")
                logger.exception(f"{self.agency}: Link: {a}")
                continue

"""


def main(site_name, url):  # noqa
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
    with open(os.path.join(Config.output_dir, 'generate.txt'), 'rt') as f:
        url, name = f.read().strip().splitlines()
    main(name, url)