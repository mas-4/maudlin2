import os
import shutil

from app.blog import Blog
from app.config import Config
from app.logger import get_logger
from app.site.agency import generate_agency_pages
from app.site.home import HomePage
from app.site.headlines import HeadlinesPage

logger = get_logger(__name__)


def copy_assets():
    for file in os.listdir(Config.assets):
        logger.debug(f"Copying %s", file)
        shutil.copy(os.path.join(Config.assets, file), Config.build)


def move_to_public():
    server_location = os.environ.get('SERVER_LOCATION', None)
    if server_location is None:
        logger.warning("No server location specified, not moving files")
        return

    for file in os.listdir(Config.build):
        logger.debug(f"Moving %s", file)
        shutil.move(os.path.join(Config.build, file), os.path.join(server_location, file))


def build_site():
    HomePage().generate()
    Blog().generate()
    HeadlinesPage().generate()
    generate_agency_pages()
    copy_assets()
    move_to_public()
