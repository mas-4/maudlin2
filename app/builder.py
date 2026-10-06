from app import ratings
from app.analysis import lean_estimate
from app.site import favicons
from app.site.common import copy_assets, clear_build, stamp_build, j2env
from app.site.data import DataHandler
from app.site.deploy import publish_to_netlify
from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_court import CourtPage
from app.site.page_edits import EditsPage
from app.site.page_emotions import EmotionsPage
from app.site.page_glossary import GlossaryPage
from app.site.page_folklore import FolklorePage
from app.site.page_rumors import RumorsPage
from app.site.page_beyond import BeyondPage
from app.site.page_motifs import MotifsPage
from app.site.page_sagas import SagasPage
from app.site.page_names import NamesPage
from app.site.page_radio import RadioPage
from app.site.page_tv import TvPage
from app.site.page_story import StoryPages
from app.site.page_saga import SagaPages
from app.site.page_methods import MethodsPage
from app.site import archive
from app.utils.config import Config
from app.utils.logger import get_logger

logger = get_logger(__name__)


def prepare():
    """Everything the pages need besides their data: outlet ratings (ratings.csv) and our lean estimates, and the
    outlet icons copied into the build. Run before any page renders, including a single page run on its own
    (`python -m app.site.page_headlines`), or chips lose their icons and ratings."""
    ratings.apply()  # outlet lean and reliability from ratings.csv
    j2env.globals['unrated'] = ratings.unrated()
    lean = lean_estimate.estimate()  # our own estimate for some unrated outlets, kept out of lean averages
    j2env.globals['lean_estimates'], j2env.globals['lean_quality'] = lean['estimates'], lean['quality']
    favicons.refresh()  # only fetches icons that are missing or a week old
    j2env.globals['icons'] = favicons.publish()
    logger.info("Prepared %d outlet icons, %d unrated outlets, %d lean estimates",
                len(j2env.globals['icons']), len(j2env.globals['unrated']), len(lean['estimates']))


def build():
    stamp_build()
    clear_build()
    prepare()
    dh: DataHandler = DataHandler()
    # Pages draw their own charts now. The election topics and election data pages (and their plots) are off for
    # now, as their events predate our data; restore them in `pages`. Polls are still fetched each run.
    pages = [HeadlinesPage, AgenciesPage, EditsPage, CourtPage, EmotionsPage, GlossaryPage, FolklorePage, RumorsPage, MotifsPage, SagasPage, SagaPages, NamesPage, RadioPage, TvPage, StoryPages, BeyondPage, MethodsPage]
    for page in pages:
        built = page(dh)
        built.generate()
        if isinstance(built, HeadlinesPage):
            archive.save(built.context.get('newsday'))  # today's front page as today's edition (not in debug)
    archive.publish()
    copy_assets()
    if Config.debug:
        # Debug builds use stale data for local previews and must never replace the live site
        logger.info("Debug build, not publishing; preview it in %s", Config.build)
        return
    publish_to_netlify()


if __name__ == '__main__':
    build()
