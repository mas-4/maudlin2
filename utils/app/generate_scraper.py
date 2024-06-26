import os
import re
import webbrowser

from app.utils import Config, Constants

TEMPLATE = """

from bs4 import BeautifulSoup as Soup

from app.utils import Bias, Credibility, Country, Constants, get_logger
from app.scraper import Scraper

logger = get_logger(__name__)


class {cls}(Scraper):
    bias = Bias.replace
    credibility = Credibility.replace
    url: str = '{url}'
    agency: str = "{site_name}"

    def setup(self, soup: Soup):
        for a in soup.find_all('a'):
            try:
                self.downstream.append((a['href'], a))
            except Exception as e:
                logger.error(f"{{self.agency}}: Error parsing link: {{e}}")
                logger.exception(f"{{self.agency}}: Link: {{a}}")
                continue

"""


def main(site_name, url):  # noqa
    class_name = site_name.replace(' ', '').replace('The', '')
    file_name = site_name.lower().replace(' ', '').replace('the', '') + '.py'
    generate_scraper(site_name, url, class_name, file_name)
    register_scraper(class_name, file_name)


def register_scraper(class_name, file_name):
    registry_path = os.path.join(Constants.Paths.ROOT, 'app', 'registry.py')
    with open(registry_path, 'rt') as f:
        registry = f.read()
    registry = f"from app.scrapers.{file_name.replace('.py', '')} import {class_name}\n" + registry
    registry = re.sub(r"Scrapers = \[", f"Scrapers = [\n    {class_name},", registry, count=1)
    with open(registry_path, 'wt') as f:
        f.write(registry)


def generate_scraper(site_name, url, class_name, file_name):
    print(f"Generating scraper for {site_name} at {url}")
    path = os.path.join(Constants.Paths.ROOT, 'app', 'scrapers', file_name)
    with open(path, "wt") as f_scraper:
        f_scraper.write(TEMPLATE.format(cls=class_name, url=url, site_name=site_name))
    print(f"Generated scraper for {site_name} at {url}")
    print(f"Opening web browser")
    url = f"https://www.google.com/search?q={site_name.replace(' ', '+')}+mediabiasfactcheck"
    webbrowser.open(url)


if __name__ == '__main__':
    with open(os.path.join(Config.data, 'generate.txt'), 'rt') as f:
        url, name = f.read().strip().splitlines()
    main(name, url)
