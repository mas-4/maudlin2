import os
import shutil

import numpy as np
from jinja2 import Environment, FileSystemLoader
from sklearn.feature_extraction.text import CountVectorizer

from app.analysis.pipelines import prepare
from app.site.wordcloudgen import PIPELINE, logger
from app.utils.config import Config
from app.utils.constants import Constants


j2env = Environment(loader=FileSystemLoader(os.path.join(Constants.Paths.ROOT, 'app', 'site', 'templates')),
                    trim_blocks=True)

class TemplateHandler:
    def __init__(self, template_name):
        self.template_name = template_name
        self.template = j2env.get_template(template_name)

    def render(self, context):
        return self.template.render(**context)

    def write(self, context, path):
        with open(path, 'wt', encoding='utf8') as f:
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
