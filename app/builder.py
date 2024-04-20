from app.site.common import copy_assets, clear_build
from app.site.deploy import publish_to_netlify
from app.site.page_agencies import AgenciesPage
from app.site.page_headlines import HeadlinesPage
from app.site.page_topics import TopicsPage
from app.utils.logger import get_logger
from app.site.data import DataHandler
from app.site.graphing import Plots

logger = get_logger(__name__)


def gen_plots(dh: DataHandler):
    Plots.sentiment_graphs(dh.all_sentiment_data)
    Plots.topic_history_bar_graph(dh.topic_df.copy())
    Plots.topic_today_bubble_graph(dh.topic_df.copy())
    Plots.topic_today_bar_graph(dh.topic_df.copy())
    Plots.individual_topic_graphs(dh.topic_df.copy(), dh.topics)


def build():
    dh: DataHandler = DataHandler()
    clear_build()
    gen_plots(dh)
    pages = [HeadlinesPage, AgenciesPage, TopicsPage]
    for page in pages:
        page().generate()
    copy_assets()
    publish_to_netlify()


if __name__ == '__main__':
    build()
