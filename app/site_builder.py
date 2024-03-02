import os
import shutil

from app.utils.config import Config
from app.utils.logger import get_logger
from app.site.blog import Blog
from app.site.agency import generate_agency_pages
from app.site.home import HomePage
from app.site.headlines import HeadlinesPage
from app.site.deploy import publish_to_netlify

logger = get_logger(__name__)


def copy_assets():
    for file in os.listdir(Config.assets):
        logger.debug(f"Copying %s", file)
        shutil.copy(os.path.join(Config.assets, file), Config.build)


def build_site():
    HomePage().generate()
    Blog().generate()
    HeadlinesPage().generate()
    generate_agency_pages()
    copy_assets()
    publish_to_netlify()


if __name__ == '__main__':
    build_site()