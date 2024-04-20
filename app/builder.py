from app.site.common import copy_assets, clear_build
from app.site.deploy import publish_to_netlify
from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_topics import TopicsPage
from app.utils.logger import get_logger

logger = get_logger(__name__)


def build():
    clear_build()
    HeadlinesPage().generate()
    AgenciesPage().generate()
    TopicsPage().generate()
    copy_assets()
    publish_to_netlify()


if __name__ == '__main__':
    build()
