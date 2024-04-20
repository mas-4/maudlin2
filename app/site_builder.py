from app.site.common import copy_assets, clear_build
from app.site.deploy import publish_to_netlify
from app.site.headlines import HeadlinesPage
from app.site.agencies import AgenciesPage
from app.site.topics import TopicsPage
from app.utils.logger import get_logger

logger = get_logger(__name__)


def build_site():
    clear_build()
    HeadlinesPage().generate()
    AgenciesPage().generate()
    TopicsPage().generate()
    copy_assets()
    publish_to_netlify()


if __name__ == '__main__':
    build_site()
