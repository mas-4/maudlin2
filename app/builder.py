from app.site.common import copy_assets, clear_build, stamp_build
from app.site.data import DataHandler
from app.site.deploy import publish_to_netlify
from app.site.graphing import Plots
from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_edits import EditsPage
from app.site.page_emotions import EmotionsPage
from app.utils.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def gen_plots(dh: DataHandler):
    Plots.sentiment_graphs(dh.all_sentiment_data)
    Plots.agency_distribution(dh.agency_data.copy())
    # The election topics and election data pages are off for now (their events predate our data); their plots
    # and pages come back by restoring them here and in `pages` below. Polls are still fetched each run.


def build():
    stamp_build()
    dh: DataHandler = DataHandler()
    clear_build()
    gen_plots(dh)
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
