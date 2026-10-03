from app.site import favicons
from app.site.common import copy_assets, clear_build, stamp_build, j2env
from app.site.data import DataHandler
from app.site.deploy import publish_to_netlify
from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_edits import EditsPage
from app.site.page_emotions import EmotionsPage
from app.utils.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def build():
    stamp_build()
    dh: DataHandler = DataHandler()
    clear_build()
    favicons.refresh()  # only fetches icons that are missing or a week old
    j2env.globals['icons'] = favicons.publish()
    # Pages draw their own charts now. The election topics and election data pages (and their plots) are off for
    # now, as their events predate our data; restore them in `pages`. Polls are still fetched each run.
    pages = [HeadlinesPage, AgenciesPage, EditsPage, EmotionsPage]
    for page in pages:
        page(dh).generate()
    copy_assets()
    if Config.debug:
        # Debug builds use stale data for local previews and must never replace the live site
        logger.info("Debug build, not publishing; preview it in %s", Config.build)
        return
    publish_to_netlify()


if __name__ == '__main__':
    build()
