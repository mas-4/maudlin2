import json
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
        context = {'page_url': page_url(path), **context}  # the page's own address, for its share card and canonical link
        with open(path, 'w', encoding='utf-8') as f:
            f.write(self.render(context))


SITE_URL = 'https://bignews.day'
SITE_DESCRIPTION = ("Nobody's immune to a good story. 145 front pages every hour, TV, radio and over a "
                    "hundred shows left and right, and our own index of the stories being told.")


def page_url(path: str) -> str:
    """A built page's public address, as Netlify serves it (no .html; the front page is the bare domain)"""
    name = os.path.relpath(path, Config.build).replace(os.sep, '/')
    if name == 'index.html':
        return SITE_URL + '/'
    return f"{SITE_URL}/{name.removesuffix('.html')}"


def motif_href(motif_id: str) -> str:
    """A motif's own page (page_motif.py), or the index page for one without a page this build (the build lists them
    in the 'motif_pages' global before any page renders)"""
    pages = j2env.globals.get('motif_pages')
    # lowercase: Netlify serves addresses lowercased and redirects /motif-M619 to /motif-m619 (Oct 27)
    return f'motif-{motif_id.lower()}.html' if pages is None or motif_id in pages else 'motifs.html'


def calculate_xkeyscore(df):
    n_features = 1000
    df['prepared'] = df['title'].apply(lambda x: prepare(x, pipeline=PIPELINE))
    dense = CountVectorizer(max_features=n_features, ngram_range=(1, 3), lowercase=False).fit_transform(
        df['prepared']
    ).todense()
    top_indices = np.argsort(np.sum(dense, axis=0).A1)[-n_features:]
    df['score'] = np.asarray(dense[:, top_indices].sum(axis=1)).ravel()  # counts are never negative
    df = df.sort_values(by=['first_accessed', 'score'], ascending=False)
    df.drop('prepared', axis=1, inplace=True)
    return df


def stylesheet() -> str:
    """The site's one stylesheet: the partials in app/site/styles joined in file-name order, which is cascade order
    (a later file's rules win over an earlier one's at equal specificity)."""
    parts = sorted(f for f in os.listdir(Config.styles) if f.endswith('.css'))
    texts = []
    for name in parts:
        with open(os.path.join(Config.styles, name), encoding='utf-8') as f:
            texts.append(f.read().rstrip('\n') + '\n')
    return '\n'.join(texts)


def copy_assets():
    for file in os.listdir(Config.assets):
        logger.debug("Copying %s", file)
        shutil.copy(os.path.join(Config.assets, file), Config.build)
    # Written after the copy, so it always replaces any style.css in the static folder
    with open(os.path.join(Config.build, 'style.css'), 'w', encoding='utf-8') as f:
        f.write(stylesheet())
    # When the site was built, for every page's "updated 12 min ago" (nav.html): one small file changes each hour
    # instead of every page
    with open(os.path.join(Config.build, 'built.json'), 'w', encoding='utf-8') as f:
        json.dump({'at': j2env.globals.get('built_at')}, f)


def clear_build():
    for file in os.listdir(Config.build):
        logger.debug("Removing %s", file)
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
j2env.globals['site_url'] = SITE_URL
j2env.globals['site_description'] = SITE_DESCRIPTION
j2env.globals['site_image'] = 'apple-touch-icon.png'  # until the build draws the site's share card (builder.prepare)
j2env.globals['motif_href'] = motif_href
j2env.globals['bias'] = Bias.to_dict()
j2env.globals['credibility'] = Credibility.to_dict()
j2env.globals['now'] = Constants.TimeConstants.now_func



def asset_version() -> str:
    """A short hash of the static files and the stylesheet, for the pages' ?v= on style.css and index.js: it changes
    when they do, so browsers fetch them again, and not otherwise, so a page doesn't change just because an hour went by"""
    import hashlib
    h = hashlib.sha1(stylesheet().encode('utf-8'))
    for name in sorted(os.listdir(Config.assets)):
        path = os.path.join(Config.assets, name)
        if os.path.isfile(path):
            with open(path, 'rb') as f:
                h.update(name.encode('utf-8') + b'\0' + f.read())
    return h.hexdigest()[:12]


def stamp_build():
    """Record when this build ran and re-render the nav bar, which shows it. Called as each build starts, not at
    import, because a run spends several minutes scraping before it builds."""
    now = dt.now(pytz.UTC)
    j2env.globals['built_at'] = now.isoformat()
    j2env.globals['build_version'] = now.strftime('%Y%m%d%H%M')  # this run's key for work shared between pages
    j2env.globals['asset_version'] = asset_version()
    j2env.globals['built_at_text'] = now.astimezone(Constants.TimeConstants.timezone).strftime(
        '%#I:%M %p ET' if os.name == 'nt' else '%-I:%M %p ET')
    from app.site.page_trackers import menus
    j2env.globals['nav'] = j2env.get_template('nav.html').render(menus=menus(published=bool(Config.netlify)))


stamp_build()
j2env.globals['footer'] = j2env.get_template('footer.html').render()
j2env.globals['enumerate'] = enumerate
# What "spicy" means wherever the site says it (tooltips)
j2env.globals['spicy_tip'] = ("Spicy means loaded wording: words the outlet chose that add emotion, judgment or alarm "
                              "beyond the facts (“slams”, “chaos”, “meltdown”). Our local language model scores "
                              "each headline 0 (plain) to 2 (built to provoke); words quoted from someone else don't "
                              "count. A word's spiciness is the average of the headlines using it.")
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


def outlet_home(name: str) -> str:
    """An outlet's homepage, from its scraper ('' when it has none)."""
    from app.registry import Scrapers
    homes = j2env.globals.setdefault('_homes', {s.agency: s.url for s in Scrapers if getattr(s, 'url', None)})
    return homes.get(name, '')


j2env.globals['outlet_home'] = outlet_home
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


def _curator_style() -> str:
    """An aggregator's chip: the same neutral chip for every one, whatever its lean (they link stories, they don't
    cover them; Oct 27: Political Wire's lean estimate made its chip a dashed blue that read as selected)"""
    from app.site.graphing import bias_colors, bias_ink
    return f'background-color: {bias_colors[3]}; color: {bias_ink[3]}'


j2env.globals['curator_style'] = _curator_style()
j2env.globals['FileNames'] = PathHandler.FileNames


def date(value):
    return value.strftime(Config.strf)


j2env.filters['date'] = date
j2env.filters['markdown'] = mistune.markdown
# </editor-fold>
