import os
import shutil

import mistune
import numpy as np
from jinja2 import Environment, FileSystemLoader
from sklearn.feature_extraction.text import CountVectorizer

from app.analysis.pipelines import prepare
from app.site.wordcloudgen import PIPELINE, logger
from app.utils.config import Config
from app.utils.constants import Constants, Bias, Credibility

j2env = Environment(loader=FileSystemLoader(os.path.join(Constants.Paths.ROOT, 'app', 'site', 'templates')),
                    trim_blocks=True)


class TemplateHandler:
    def __init__(self, template_name: str, name: str = None):
        self.template_name = template_name
        self.template = j2env.get_template(template_name)
        if name is None:
            name = template_name
        self.path = os.path.join(Config.build, name)

    def render(self, context):
        return self.template.render(**context)

    def write(self, context, path: str = None):
        if path is None:
            path = self.path
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.render(context))


def calculate_xkeyscore(df):
    n_features = 1000
    df['prepared'] = df['title'].apply(lambda x: prepare(x, pipeline=PIPELINE))
    dense = CountVectorizer(max_features=n_features, ngram_range=(1, 3), lowercase=False).fit_transform(
        df['prepared']
    ).todense()
    top_indices = np.argsort(np.sum(dense, axis=0).A1)[-n_features:]
    df['score'] = [sum(doc[0, i] for i in top_indices if doc[0, i] > 0) for doc in dense]
    df = df.sort_values(by=['first_accessed', 'score'], ascending=False)
    df.drop('prepared', axis=1, inplace=True)
    return df


def copy_assets():
    for file in os.listdir(Config.assets):
        logger.debug(f"Copying %s", file)
        shutil.copy(os.path.join(Config.assets, file), Config.build)


def clear_build():
    for file in os.listdir(Config.build):
        logger.debug(f"Removing %s", file)
        os.remove(os.path.join(Config.build, file))


class PathHandler:
    class FileNames:
        main_wordcloud = 'wordcloud.png'
        sentiment_graphs = 'sentiment-graphs.png'
        topic_history_bar_graph = 'topic_history_bar_graph.png'
        topic_history_stacked_area = 'topic_history_stacked_area.png'
        topic_today_bubble_graph = 'topic_today_bubble_graph.png'
        topic_today_bar_graph = 'topic_today_bar_graph.png'
        agency_distribution = 'agency_distribution.png'
        mentions_graph = 'mentions_graph.png'

    def __init__(self, filename: str):
        self.filename = filename

    @property
    def build(self):
        return os.path.join(Config.build, self.filename)

    @property
    def path(self):
        return self.filename


# <editor-fold desc="Jinja2 Environment Stuff">
j2env.globals['Config'] = Config
j2env.globals['bias'] = Bias.to_dict()
j2env.globals['credibility'] = Credibility.to_dict()
j2env.globals['now'] = Constants.TimeConstants.now_func

j2env.globals['nav'] = j2env.get_template('nav.html').render()
j2env.globals['footer'] = j2env.get_template('footer.html').render()
j2env.globals['enumerate'] = enumerate
j2env.globals['FileNames'] = PathHandler.FileNames


def date(value):
    return value.strftime(Config.strf)


j2env.filters['date'] = date
j2env.filters['markdown'] = mistune.markdown
# </editor-fold>
