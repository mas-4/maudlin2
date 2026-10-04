import os
import shutil

from markupsafe import Markup, escape
from datetime import datetime as dt

import mistune
import numpy as np
import pytz
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
        path = os.path.join(Config.build, file)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


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
        framing = 'framing.png'
        loaded_language = 'loaded_language.png'
        generic_ballot = 'generic_ballot.png'
        approval = 'approval.png'

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



def stamp_build():
    """Record when this build ran and re-render the nav bar, which shows it. Called as each build starts, not at
    import, because a run spends several minutes scraping before it builds."""
    now = dt.now(pytz.UTC)
    j2env.globals['built_at'] = now.isoformat()
    j2env.globals['build_version'] = now.strftime('%Y%m%d%H%M')
    j2env.globals['built_at_text'] = now.astimezone(Constants.TimeConstants.timezone).strftime(
        '%#I:%M %p ET' if os.name == 'nt' else '%-I:%M %p ET')
    j2env.globals['nav'] = j2env.get_template('nav.html').render()


stamp_build()
j2env.globals['footer'] = j2env.get_template('footer.html').render()
j2env.globals['enumerate'] = enumerate
# Every page's feeling emoji come from the one table in newsfilter, so changing one is a one-line edit
from app.analysis.newsfilter import EMOTION_EMOJI, EMOTION_BOOKENDS  # noqa: E402
j2env.globals['emotion_emoji'] = EMOTION_EMOJI
j2env.globals['cloud_bookends'] = {EMOTION_EMOJI[e]: list(pair) for e, pair in EMOTION_BOOKENDS.items()}
j2env.globals['icons'] = {}  # outlet name -> icon path, filled by the build (see favicons.publish)
# What one page learns that a later one needs during a build (the front page's stories, for the outlet pages)
SHARED: dict = {}


def outlet_icon(name: str) -> Markup:
    """An outlet's icon for the front of its chip: its favicon on a white disc, or its initial when it has none."""
    path = j2env.globals['icons'].get(name)
    if path:
        return Markup(f'<img class="outlet-icon" src="{escape(path)}" alt="" loading="lazy">')
    initial = (name.removeprefix('The ').strip()[:1] or '?').upper()
    return Markup(f'<span class="outlet-icon outlet-mono" aria-hidden="true">{escape(initial)}</span>')


j2env.globals['outlet_icon'] = outlet_icon

# Chip labels for outlets whose full names blow up their chips; the full name shows on hover
SHORT_NAMES = {
    'Radio Free Europe Radio Liberty': 'RFE/RL', 'The Christian Science Monitor': 'CS Monitor',
    'Independent Journal Review': 'IJR', 'The Washington Free Beacon': 'Free Beacon',
    'One America News Network': 'OAN', 'South China Morning Post': 'SCMP', 'The Wall Street Journal': 'WSJ',
}


def short_name(name: str) -> str:
    return SHORT_NAMES.get(name, name)


j2env.globals['short_name'] = short_name
j2env.globals['short_names'] = SHORT_NAMES
j2env.globals['unrated'] = set()  # outlets AllSides doesn't rate, filled by the build
j2env.globals['lean_estimates'] = {}  # our estimate for some of them (app/analysis/lean_estimate.py)
j2env.globals['lean_quality'] = None


def chip_style(name: str, bias: int) -> str:
    """An outlet chip's colors: its lean color, or a dashed white chip when its lean isn't rated."""
    from app.site.graphing import bias_colors, bias_ink
    if name in j2env.globals['lean_estimates']:  # our estimate: its lean color, dashed to say it isn't a rating
        lean = j2env.globals['lean_estimates'][name]
        return f'background-color: {bias_colors[lean + 3]}; color: {bias_ink[lean + 3]}; border-style: dashed'
    if name in j2env.globals['unrated']:
        return 'background-color: #ffffff; color: #1f1f2e; border-style: dashed'
    return f'background-color: {bias_colors[int(bias) + 3]}; color: {bias_ink[int(bias) + 3]}'


j2env.globals['chip_style'] = chip_style
j2env.globals['FileNames'] = PathHandler.FileNames


def date(value):
    return value.strftime(Config.strf)


j2env.filters['date'] = date
j2env.filters['markdown'] = mistune.markdown
# </editor-fold>
