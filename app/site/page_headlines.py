import json
import os
import re
from collections import defaultdict
from datetime import datetime as dt, timedelta as td
from typing import Optional

import numpy as np
import pytz
import pandas as pd
from sqlalchemy import func

from app.analysis.clustering import prepare_embedding_cosine, story_similarity, form_clusters, label_clusters, embed, \
    unlink_money_conflicts
from app.analysis.sagas import link_sagas
from app.analysis import trends_meter
from app.analysis.quotes import story_quotes
from app.analysis.wording import side_phrases
from app.investigations import recent as recent_investigations
from app import sidefeeds
from app.analysis.stories import sync_stories, label_stories, headline_sentiment
from app.analysis import llm, textnorm
from app.analysis.pipelines import Pipelines, prepare
from app.site.common import SHARED, calculate_xkeyscore, chip_style, copy_assets, outlet_icon, short_name, TemplateHandler
from app.models import Session, Headline
from app.site.data import DataHandler, DataTypes
from app.analysis.edits import find_edits
from app.analysis.newsfilter import EMOTION_EMOJI, EMOTIONS, emotion_weights
from app.site.wordcloudgen import cloud_words
from app.site.graphing import bias_colors, bias_ink
from app.utils import Config, Country, get_logger
from app.registry import Scrapers
from app.trends import current_trends, match_text

logger = get_logger(__name__)

TRENDING_COUNT = 10
BREAKING_MINUTES = 90
# A story gets the churn badge once at least this many of its outlets, and this share of them, have rewritten
# their headline: 3 rewrites is a lot for a 6-outlet story and ordinary for a 38-outlet one
CHURN_OUTLETS = 3
CHURN_SHARE = 0.15
STORY_EMOTION_SHARE = 0.2  # of the story's averaged emotion votes, for a feeling badge
# Outlet chips on story cards: new ones get a sparkle, dropped ones fade over a day down to a ghost
FRESH_HOURS = 2
GHOST_FADE_HOURS = 12
GHOST_OPACITY = 0.35
# Share of active outlets on the biggest story, highest tier first. A starting point, to tune with a few weeks of data.
NEWS_DAY_TIERS = [('big', 0.45), ('normal', 0.25), ('slow', 0.0)]  # on the age-weighted share, see news_day
NEWS_DAY_FRESH_HOURS = 12
SAGA_COLORS = ['#ff4fa3', '#3a86ff', '#00c2a8', '#ff6b1a', '#7a5cff', '#ffc400']
INVESTIGATION_MATCH = 0.55  # title similarity to tie an investigation to a current story
BLINDSPOT_MIN_OUTLETS = 6  # rated outlets covering a story before its lopsidedness means much
# Aggregators mostly link to other outlets' stories, so they don't count as outlets covering a story (or as votes in
# the cloud); a story card says when they're picking it up instead (#151)
AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire'}
CURATOR_MATCH = 0.7  # an aggregator's headline this close to one of a story's headlines links to that story
BLINDSPOT_SHARE = 0.7  # of them from one side
BLINDSPOT_LIFT = 1.5  # and at least this many times that side's share of all rated outlets
BREAK_WINDOW_MINUTES = 75  # "within the hour" across two hourly scrapes, with slack for scrape timing
FAST_BREAK = 8  # outlets within that window to count as a fast break
NEWS_DAY_HALF_LIFE_HOURS = 24
# Each verdict is anchored by a big emoji on either side
NEWS_DAY_LABELS = {
    'big': {'emoji': '🚨', 'ends': ('🚨', '🚨'), 'label': 'Big news day!'},
    'normal': {'emoji': '📰', 'ends': ('📰', '🗞️'), 'label': 'Just another news day'},
    'slow': {'emoji': '🌴🐢', 'ends': ('🌴', '🐢'), 'label': 'Slow news day…'},
}
# e.g. "Oct 3, 9:41 AM ET"; Windows' strftime doesn't support the no-padding dash
TOOLTIP_TIME = '%b %#d, %#I:%M %p ET' if os.name == 'nt' else '%b %-d, %-I:%M %p ET'
# Cosine between a trend and a story's mean headline embedding. On a day of data true matches scored 0.72-0.86
# and the best non-match 0.48 (bare Wikipedia names score low either way, so they also match by name)
TREND_MATCH_THRESHOLD = 0.65
NAME_MATCH_HEADLINES = 2
TREND_SOURCES = [
    {'key': 'bluesky', 'name': 'Bluesky', 'heading': 'Trending on Bluesky', 'unit': 'posts'},
    {'key': 'google', 'name': 'Google', 'heading': 'Trending Google searches', 'unit': 'searches'},
    {'key': 'wikipedia', 'name': 'Wikipedia', 'heading': 'Most read on Wikipedia', 'unit': 'views'},
    {'key': 'mastodon', 'name': 'Mastodon', 'heading': 'Shared on Mastodon', 'unit': 'people'},
]


# Meter scales: lean ran L+1.2 to R+2.0 on a day of stories; mood is the event score halved, so -1 to 1
LEAN_RANGE = 2.0
MOOD_RANGE = 1.0


def meter(value: float, scale: float, negative: str, positive: str) -> dict:
    """A diverging meter: `position` is 0-100 (50 is neutral, clamped at the ends) plus a short text value."""
    position = 50 + 50 * max(-1.0, min(1.0, value / scale))
    if abs(value) < scale * 0.05:
        text = 'even' if negative else '0.00'
    elif negative:
        text = f'{negative if value < 0 else positive}+{abs(value):.1f}'
    else:
        text = f'{value:+.2f}'
    return {'value': round(float(value), 3), 'position': round(position, 1), 'text': text}


DB_START = dt(2000, 1, 1)  # our first scrape, set when the page is generated


def first_scrape() -> dt:
    with Session() as s:
        return s.query(func.min(Headline.first_accessed)).scalar() or dt(2000, 1, 1)


def break_speed(headlines: list[dict]) -> Optional[int]:
    """How fast a story broke: how many outlets had it within about an hour of our first sighting (the first two
    hourly scrapes). None for stories already running when the database started, whose first sighting is ours, not
    theirs."""
    starts = sorted(pd.Timestamp(h['first_seen']) for h in headlines)
    db_start = pd.Timestamp(DB_START)
    if starts and starts[0].tzinfo is not None and db_start.tzinfo is None:
        db_start = db_start.tz_localize('UTC')  # the database stores UTC without saying so
    if not starts or starts[0] - db_start < td(hours=2):
        return None
    by_outlet = {}
    for h in headlines:
        seen = pd.Timestamp(h['first_seen'])
        by_outlet[h['agency']] = min(by_outlet.get(h['agency'], seen), seen)
    return sum(t - starts[0] <= td(minutes=BREAK_WINDOW_MINUTES) for t in by_outlet.values())


def weather(mood: float) -> tuple[str, str]:
    """A story's mood (-1 grim to 1 upbeat) as weather, matching the headline table's mood badges."""
    if mood <= -0.6:
        return '⛈️', 'grim+'
    if mood <= -0.2:
        return '🌧️', 'grim'
    if mood < 0.2:
        return '🍞', 'plain'
    if mood < 0.6:
        return '🌤️', 'upbeat'
    return '☀️', 'upbeat+'


def _name(text: str) -> str:
    """A trend's name for exact matching: no parenthetical, hyphens as spaces, lowercase."""
    return re.sub(r'\s+', ' ', re.sub(r'\(.*?\)', '', text).replace('-', ' ')).strip().lower()


def age_text(hours: float) -> str:
    if hours < 1:
        return f'{max(1, round(hours * 60))} min'
    if hours < 48:
        return f'{round(hours)} hour{"" if round(hours) == 1 else "s"}'
    return f'{round(hours / 24)} days'


TABLE_FILE = 'headlines-table.json'

# Sort buttons over each card's outlet chips; the page script reorders chips by their data attributes
SORT_BAR = ('<div class="chip-sort" role="group" aria-label="Sort outlets">sort: '
            '<button data-key="bias" class="active">bias</button>'
            '<button data-key="first">first seen</button>'
            '<button data-key="live">still showing</button>'
            '<button data-key="mood">mood</button>'
            '<button data-key="framing">framing</button>'
            '<span class="sort-legend">outlets left to right, colored by lean</span></div>')


def story_feelings(group) -> list[dict]:
    """The feelings a story stirs, ranked-choice style (each headline's vote split across its ranked emotions,
    averaged over the story): every one other than neutral with at least STORY_EMOTION_SHARE of the votes, strongest
    first, at most three."""
    votes = [emotion_weights(r) for r in group.get('emotion_ranks', pd.Series(dtype=object)) if isinstance(r, str)]
    if not votes:
        return []
    feelings = pd.DataFrame(votes).reindex(columns=EMOTIONS, fill_value=0).fillna(0).mean().drop('neutral')
    strong = feelings[feelings >= STORY_EMOTION_SHARE].sort_values(ascending=False).head(3)
    return [{'emoji': EMOTION_EMOJI[e], 'name': e, 'share': round(100 * v)} for e, v in strong.items()]


def dominant_emotion(group) -> dict:
    """The story's strongest feeling (see story_feelings), or {} when none is strong enough."""
    feelings = story_feelings(group)
    return feelings[0] if feelings else {}


def match_trends_to_stories(df, trends) -> dict[str, int]:
    """Trend topic id -> the cluster it's about, for trends that match a story.

    Two ways to match. Sentence-like trends (Bluesky topics, Google searches, shared links) are compared by
    embedding with the story's average headline. Bare names (a Wikipedia article like "Christa Pike") carry too
    little meaning for that, so a trend also matches when its full name, two words or more, appears in at least
    two of a story's headlines."""
    if not trends or df.empty:
        return {}
    clusters = sorted(df['cluster'].unique())
    E = embed(df['title'].tolist())
    E /= np.linalg.norm(E, axis=1, keepdims=True)
    positions = {c: np.flatnonzero(df['cluster'].to_numpy() == c) for c in clusters}
    centroids = np.array([E[positions[c]].mean(axis=0) for c in clusters])
    centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
    T = embed([match_text(t) for t in trends])
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    similarity = T @ centroids.T
    headlines = {c: [_name(t) for t in df['title'].iloc[positions[c]]] for c in clusters}

    matches = {}
    for trend, row in zip(trends, similarity):
        name = _name(trend.display_name)
        if len(name.split()) >= 2:
            mentions = {c: sum(name in h for h in headlines[c]) for c in clusters}
            best = max(mentions, key=mentions.get)
            if mentions[best] >= NAME_MATCH_HEADLINES:
                matches[trend.topic] = best
                continue
        if row.max() >= TREND_MATCH_THRESHOLD:
            matches[trend.topic] = clusters[row.argmax()]
    return matches

pipeline = [
    textnorm.hyphenated_words,
    textnorm.quotation_marks,
    textnorm.normalize_unicode,
    textnorm.whitespace,
    textnorm.accents,
    textnorm.brackets,
    textnorm.punctuation,
    str.lower,
    Pipelines.tokenize,
    Pipelines.decontract,
    ' '.join
]


def pack_table(rows: list[dict]) -> dict:
    """The table's rows as published: one list per row instead of named fields, with the values that repeat across
    rows (outlets with their lean, topics, stories, feelings) listed once and referred to by position, and URLs
    without "https://". About a tenth smaller over the wire than named fields (repeated keys mostly compress away
    anyway; the bulk is the URLs and titles). The page unpacks it (unpackTable in headlines.html) back into the rows
    table_rows makes, and the download button saves those, named fields and all."""
    outlets, topics, stories, feelings, packed = {}, {}, {}, {}, []
    for r in rows:
        outlet = outlets.setdefault((r['agency'], r['bias'], r['rated']), len(outlets))
        topic = topics.setdefault(r['topic'], len(topics)) if r['topic'] else None
        if r['story'] is not None:
            stories[str(r['story'])] = [r['story_title'], r['story_size']]
        url = r['url'][len('https://'):] if r['url'].startswith('https://') else r['url']
        packed.append([outlet, url, r['title'], r['seen'], r['buzz'], topic, r['mood'], r['loaded'],
                       [feelings.setdefault(name, len(feelings)) for _, name in r['feelings']], r['story']])
    return {'version': 1, 'outlets': [list(o) for o in outlets], 'topics': list(topics), 'stories': stories,
            'feelings': [[EMOTION_EMOJI[name], name] for name in feelings],
            'columns': ['outlet', 'url', 'title', 'seen', 'buzz', 'topic', 'mood', 'loaded', 'feelings', 'story'],
            'rows': packed}


def unpack_table(data: dict) -> list[dict]:
    """pack_table undone, field for field as unpackTable does it in the page (kept in step by the tests)."""
    rows = []
    for outlet, url, title, seen, buzz, topic, mood, loaded, feelings, story in data['rows']:
        agency, bias, rated = data['outlets'][outlet]
        name = data['topics'][topic] if topic is not None else ''
        title_size = data['stories'].get(str(story), ['', 0]) if story is not None else ['', 0]
        rows.append({'agency': agency, 'bias': bias, 'rated': rated,
                     'url': url if url.startswith('http') else 'https://' + url, 'title': title, 'seen': seen,
                     'buzz': buzz, 'topic': name, 'topic_url': f"{name.replace(' ', '_')}.html" if name else '',
                     'mood': mood, 'loaded': loaded, 'feelings': [data['feelings'][i] for i in feelings],
                     'story': story, 'story_title': title_size[0], 'story_size': title_size[1]})
    return rows


class HeadlinesPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('headlines.html', 'index.html')
        # The headline table has a page of its own, rendered from the same template (`page_part` picks the sections)
        self.table_page = TemplateHandler('headlines.html', 'headlines.html')
        self.newsletter = TemplateHandler('newsletter.html')
        self.context = {'title': 'Current Headlines', 'breaking_minutes': BREAKING_MINUTES}

    def generate(self):
        logger.info("Generating headlines page...")
        main = self.dh.main_headline_df
        cloud = main[~main['agency'].isin(AGGREGATORS)][['title', 'agency', 'bias', 'rated', 'url', 'afinn',
                                                         'vader_compound', 'event_score', 'loaded_score',
                                                         'emotion_ranks']].copy()
        cloud['sentiment'] = headline_sentiment(cloud)
        self.context['cloud_words'] = cloud_words(cloud)
        self.context['bias_colors'] = bias_colors
        self.context['bias_ink'] = bias_ink
        df = self.filter_score_sort(self.dh.main_headline_df.copy())
        # Stories draw on the last day of headlines, keeping the raw times the cards need before they're formatted
        stories = self.dh.story_headline_df.copy()
        stories['first_seen'], stories['last_seen'] = stories['first_accessed'], stories['last_accessed']
        self.cluster_and_summarize(self.filter_score_sort(stories))
        # The table's rows ship as their own file, fetched when the reader scrolls near the table: there are
        # thousands, and inline they'd make the front page several megabytes
        with open(os.path.join(Config.build, TABLE_FILE), 'w') as f:
            json.dump(pack_table(self.table_rows(df)), f, separators=(',', ':'), ensure_ascii=False)
        self.context['table_file'] = TABLE_FILE
        # Saved under a dated name, so a reader's downloads from different hours don't overwrite each other
        self.context['table_download'] = f"bignews-headlines-{pd.Timestamp.now(tz='US/Eastern'):%Y-%m-%d-%H%M}.json"
        self.newsletter.write(self.context)
        self.write_feed()
        self.template.write({**self.context, 'page_part': 'front'})
        self.table_page.write({**self.context, 'page_part': 'table', 'title': 'Every Headline'})
        logger.info("...done")

    @staticmethod
    def heat(df) -> pd.DataFrame:
        """Per story (or saga, by df['group']): outlets carrying it on their front page now, its age (from its oldest
        headline), and a score: its share of the outlets on front pages now, at full weight for NEWS_DAY_FRESH_HOURS,
        then halving every NEWS_DAY_HALF_LIFE_HOURS. The news-day sticker and the trending list both rank by it."""
        live = df[df['live']]
        live_outlets = max(1, live['agency'].nunique())
        heat = pd.DataFrame({'now': live.groupby('group')['agency'].nunique()}).reindex(df['group'].unique()).fillna(0)
        heat['age'] = df.groupby('group')['howlong'].max()
        hours = heat['age'] / 3600
        heat['score'] = heat['now'] / live_outlets * 0.5 ** (
            (hours - NEWS_DAY_FRESH_HOURS).clip(lower=0) / NEWS_DAY_HALF_LIFE_HOURS)
        return heat

    def write_feed(self):
        """feed.xml: the trending stories as RSS (#123). Each item keeps its saved story's id as its guid, so readers
        don't show a story again when its rank or title changes."""
        from email.utils import format_datetime
        by_id = {c['cluster']: c for c in self.context.get('clusters', [])}
        story_of = getattr(self, 'story_of', {})
        now = dt.now(pytz.UTC)
        items = []
        for t in self.context.get('news_trends', []):
            c = by_id.get(t['cluster'])
            if not c:
                continue
            first = now - td(seconds=float(c['first']))
            bits = [f"On {t['now']} outlets' front pages now ({t['outlets']} in all)",
                    f"covered by {c['lean']['text']} outlets", f"mood {c['mood']['word']}"]
            if c.get('feelings'):
                bits.append('feelings: ' + ', '.join(f"{f['emoji']} {f['name']}" for f in c['feelings']))
            if t.get('saga'):
                bits.append(f"part of a {t['saga']}-part saga")
            items.append({'title': t['title'], 'cluster': t['cluster'], 'guid': story_of.get(t['cluster'], t['cluster']),
                          'date': format_datetime(first), 'description': '; '.join(bits) + '.'})
        TemplateHandler('feed.xml').write({'feed_items': items, 'feed_date': format_datetime(now)})

    def news_day(self, df, active_outlets: int):
        """How big a news day it is: the share of outlets carrying a story on their front page right now, for the
        story where that's highest once age is weighed in. One fresh story everyone is covering makes a big news day;
        a story stays at full weight for NEWS_DAY_FRESH_HOURS from its first sighting, then halves every
        NEWS_DAY_HALF_LIFE_HOURS, so yesterday's blockbuster that's still on every front page fades out. Needs no
        historical baseline. (Ages count from our own first sighting, so stories already running when the database
        started look younger than they are.)"""
        live = df[df['live']]
        live_outlets = live['agency'].nunique()
        if live.empty or not live_outlets:
            self.context['newsday'] = None
            return
        # A story is as old as its oldest headline in the window; outlets keep posting fresh articles on a running
        # story, so a typical article's age would make it look new
        # A saga counts as one story here
        ages = df.groupby('group')['howlong'].max()
        stories = live.groupby('group').agg(outlets=('agency', 'nunique'))
        stories['age'] = ages.reindex(stories.index)
        stories['share'] = stories['outlets'] / live_outlets
        hours = stories['age'] / 3600
        stories['score'] = stories['share'] * 0.5 ** ((hours - NEWS_DAY_FRESH_HOURS).clip(lower=0) / NEWS_DAY_HALF_LIFE_HOURS)
        top = stories['score'].idxmax()
        score = stories.loc[top, 'score']
        sagas = self.context.get('sagas', {})
        kind = next(k for k, threshold in NEWS_DAY_TIERS if score >= threshold)
        logger.info("News day: %s (top story on %.0f%% of outlets, %.0fh old, score %.2f)",
                    kind, 100 * stories.loc[top, 'share'], hours[top], score)
        self.context['newsday'] = {
            **NEWS_DAY_LABELS[kind], 'kind': kind, 'share': round(100 * stories.loc[top, 'share']),
            'outlets': int(stories.loc[top, 'outlets']), 'active': live_outlets,
            'story': sagas[top]['name'] if top in sagas else self.context['titles'][top],
            'cluster': int(sagas[top]['lead'] if top in sagas else top), 'age': age_text(hours[top]),
            # What we're tracking right now: news headlines on front pages, and the stories they form
            'live_headlines': int(self.dh.main_headline_df['live'].sum()),
            'stories': len(self.context.get('clusters', [])),
        }

    def cluster_and_summarize(self, df):
        global DB_START
        DB_START = first_scrape()
        n_samples_per_cluster = 6
        df = df[
            (df['country'] == Country.us.name)
            |
            (
                    (df['country'] == Country.gb.name)
                    &
                    (df['agency'].isin(Config.exempted_foreign_media))
            )
            ].copy()
        # Aggregators sit out of the stories themselves; afterwards they're matched to the stories they're linking
        self.curated = df[df['agency'].isin(AGGREGATORS) & df['live'].astype(bool)].copy()
        df = df[~df['agency'].isin(AGGREGATORS)].copy()
        df['processed'] = df['title'].apply(lambda x: prepare(x, pipeline))

        # Partisan lean is measured against the outlets in today's pool, which lean one way themselves
        # (outlets without a lean rating are left out of lean)
        baseline_bias = df[df['rated'].astype(bool)].drop_duplicates('agency')['bias'].mean()
        active_outlets = df['agency'].nunique()
        logger.info("Clustering %i headlines", len(df))
        df = df.reset_index(drop=True)  # cluster ids are positional
        similarity, threshold, model = story_similarity(df['title'])
        similarity = unlink_money_conflicts(similarity, df['title'].tolist())
        logger.info("Story similarity from %s, threshold %.2f", model, threshold)
        clusters = form_clusters(similarity, n_samples_per_cluster, threshold)
        logger.info("%i clusters formed", len(clusters))

        df = label_clusters(df, clusters)
        considered = df  # every headline, for sagas to pull in related ones that made no story
        df = df[df['cluster'] != -1].copy()
        # One headline per outlet per story: the one still on its front page if there is one
        df = df.sort_values('live', ascending=False, kind='stable')
        df.drop_duplicates(subset=['cluster', 'agency'], keep='first', inplace=True)
        df['text_length'] = df['title'].str.len()
        df = df.groupby('cluster').filter(lambda x: len(x) >= n_samples_per_cluster)
        logger.info("%i clusters left after filtering", df['cluster'].nunique())
        sentiment = df['sentiment'] = headline_sentiment(df)
        df['deviation'] = sentiment - sentiment.groupby(df['cluster']).transform('mean')
        stories = sync_stories(df)
        self.story_of = {int(k): story.id for k, story in stories.items()}  # cluster -> saved story, for sagas
        self.context['story_of'] = self.story_of  # stable ids for share links (cluster numbers change every run)
        self.summarize(df, label_stories(df, stories))
        grouped = df.groupby('cluster')
        clusters_list = [{'cluster': key, 'data': group.to_dict(orient='records')} for key, group in grouped]
        for cluster in clusters_list:
            cluster['coverage'] = round(len(cluster['data']) / len(Scrapers) * 100, 2)
            cluster['first'] = max(cluster['data'], key=lambda x: x['howlong'])['howlong']
            group = df[df['cluster'] == cluster['cluster']]
            rated = group[group['rated'].astype(bool)]
            cluster['lean'] = meter(rated['bias'].mean() - baseline_bias if not rated.empty else 0.0,
                                    LEAN_RANGE, 'L', 'R')
            cluster['mood'] = meter(headline_sentiment(group).mean(), MOOD_RANGE, '', '')
            cluster['mood'].update(dict(zip(('emoji', 'word'), weather(cluster['mood']['value']))))
            cluster['feelings'] = story_feelings(group)
            cluster['emotion'] = cluster['feelings'][0] if cluster['feelings'] else {}
            cluster['speed'] = break_speed(cluster['data'])
            cluster['outlets'] = int(group['agency'].nunique())
            cluster['spice'] = round(float(group['loaded_score'].mean()), 3) if group['loaded_score'].notna().any() else 0
            cluster['quotes'] = story_quotes(cluster['data'])
            cluster['wording'] = side_phrases(cluster['data'])

        # Sagas: stories that are parts of one running story, kept across days (earlier parts stay in the saga after
        # they leave the front pages). Members sit together, ordered by the saga's newest part
        sagas = link_sagas(considered, df, getattr(self, 'story_of', {}))
        saga_of = {k: sid for sid, saga in sagas.items() for k in saga['clusters']}
        age = {c['cluster']: c['first'] for c in clusters_list}
        for sid, saga in sagas.items():
            saga['color'] = SAGA_COLORS[saga['id'] % len(SAGA_COLORS)]  # a saga keeps its color from run to run
            saga['lead'] = max(saga['clusters'], key=lambda k: (df['cluster'] == k).sum())  # its biggest story now
            saga['clusters'].sort(key=lambda k: -age[k])  # in the order they broke
            # Part numbers count every part, earlier ones included, in the order they were first seen
            saga['part_of'] = {p['cluster']: n for n, p in enumerate(saga['parts_all'], start=1) if p['cluster'] is not None}
        for cluster in clusters_list:
            sid = saga_of.get(cluster['cluster'])
            cluster['saga'] = {**sagas[sid], 'id': sid} if sid is not None else None
        newest = {}
        for cluster in clusters_list:
            key = saga_of.get(cluster['cluster'], ('story', cluster['cluster']))
            newest[key] = min(newest.get(key, cluster['first']), cluster['first'])
        clusters_list.sort(key=lambda c: (newest[saga_of.get(c['cluster'], ('story', c['cluster']))],
                                          saga_of.get(c['cluster'], -1), c['first']))
        self.context['sagas'] = sagas
        by_id = {c['cluster']: c for c in clusters_list}
        now = dt.now(pytz.UTC).replace(tzinfo=None)
        for saga in sagas.values():
            saga['parts'] = []
            for part in saga['parts_all']:
                k = part['cluster']
                if k is not None and k in by_id:  # on the front pages now: links to its card
                    saga['parts'].append({'cluster': int(k), 'title': self.context['titles'][k], 'now': True,
                                          'outlets': by_id[k]['outlets'], 'age': age_text(by_id[k]['first'] / 3600),
                                          'feelings': by_id[k]['feelings'][:1]})
                else:  # a part that has left the front pages (not necessarily an older one)
                    saga['parts'].append({'cluster': None, 'title': part['label'] or 'An earlier part', 'now': False,
                                          'outlets': part['outlets'],
                                          'age': age_text((now - part['first_seen']).total_seconds() / 3600),
                                          'feelings': []})
            saga['started'] = saga['parts'][0]['age']
        self.context['saga_list'] = sorted(sagas.values(), key=lambda s: -s['outlets'])
        df['group'] = df['cluster'].map(lambda k: saga_of.get(k, k))
        self.curators(df, clusters_list)
        self.meter_trends(clusters_list)
        self.make_agency_lists(clusters_list)
        # For the outlet pages: which current story each headline (by url) belongs to
        SHARED['story_of_url'] = {a['url']: (int(c['cluster']), self.context['titles'][c['cluster']])
                                  for c in clusters_list for a in c['data']}
        self.context['clusters'] = clusters_list
        self.trending_in_the_news(df)
        self.blindspots(clusters_list)
        self.investigations(clusters_list)
        self.shows(clusters_list)
        self.show_coverage(clusters_list)
        self.news_day(df, active_outlets)

    def trending_in_the_news(self, df):
        """Our own trending list, ranked by how many outlets carry each story, next to what's trending on social
        media, search and Wikipedia. Where a trend and a story are about the same thing both get marked, so the
        overlap (and the gap) between what the press covers and what people pay attention to is visible."""
        outlets = df.groupby('cluster')['agency'].nunique().sort_values(ascending=False)
        speeds = {c['cluster']: c['speed'] for c in self.context.get('clusters', [])
                  if c.get('speed') and c['speed'] >= FAST_BREAK}
        logger.info("Break speeds (outlets in the first hour): %s",
                    sorted((c.get('speed') for c in self.context.get('clusters', []) if c.get('speed') is not None),
                           reverse=True)[:10])
        boxes = []
        on = {}  # cluster -> names of the sources where it's trending
        for source in TREND_SOURCES:
            trends = current_trends(source['key'])
            if not trends:
                continue
            matches = match_trends_to_stories(df, trends)
            for cluster in matches.values():
                on.setdefault(cluster, []).append(source['name'])
            boxes.append({**source, 'trends': trends, 'matches': matches})
        self.context['trend_boxes'] = boxes
        # A saga counts once, with every outlet on any of its parts (and on related headlines that made no story).
        # Ranked by heat, not reach: how many outlets carry it on their front page *now*, weighed by age the same way
        # as the news-day sticker, so a story outlets have dropped falls down the list instead of holding its spot
        # for a day on yesterday's coverage
        sagas = self.context.get('sagas', {})
        reach = df.groupby('group')['agency'].nunique()
        for sid, saga in sagas.items():
            reach[sid] = saga['outlets']
        heat = self.heat(df)
        items = []
        for group in heat[heat['now'] > 0].sort_values('score', ascending=False).head(TRENDING_COUNT).index:
            count = reach[group]
            saga = sagas.get(group)
            members = saga['clusters'] if saga else [group]
            lead = saga['lead'] if saga else group
            items.append({'cluster': lead, 'title': saga['name'] if saga else self.context['titles'][group],
                          'outlets': int(count), 'now': int(heat.loc[group, 'now']),
                          'saga': saga['size'] if saga else None,
                          'color': saga['color'] if saga else None,
                          'speed': max((speeds.get(k) or 0) for k in members) or None,
                          'also_on': sorted({name for k in members for name in on.get(k, [])})})
        self.context['news_trends'] = items

    def investigations(self, clusters_list):
        """The newest pieces from open-source and investigative outfits (app/investigations.py), each pointed at the
        current story it's about when one is close enough in meaning."""
        pieces = recent_investigations()
        if pieces and clusters_list:
            ids = [c['cluster'] for c in clusters_list]
            titles = [self.context['titles'][k] for k in ids]
            vectors = embed([p['title'] for p in pieces] + titles)
            vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
            similarity = vectors[:len(pieces)] @ vectors[len(pieces):].T
            for piece, row in zip(pieces, similarity):
                best = int(row.argmax())
                piece['story'] = int(ids[best]) if row[best] >= INVESTIGATION_MATCH else None
                piece['story_title'] = titles[best] if piece['story'] is not None else None
        for piece in pieces:
            piece.setdefault('story', None)  # no current stories to match: no "in the news" link
            piece.setdefault('story_title', None)
            piece['date'] = pd.Timestamp(piece['published']).tz_convert('US/Eastern').strftime('%b %-d')
        self.context['investigations'] = pieces

    SHOW_KIND = {'podcast': '🎙️', 'newsletter': '📨', 'video': '📺'}
    SHOW_GROUP = {'left': '#3a86ff', 'right': '#ff4f6d', 'center': '#b8b8c8', 'crossover': '#8a5cff'}

    def shows(self, clusters_list):
        """The newest from news-of-the-day newsletters, podcasts and political video channels (app/sidefeeds.py), one
        per source, each pointed at the current story it's about when one is close enough in meaning."""
        try:
            items = sidefeeds.recent()
        except Exception as e:  # noqa: e.g. the table doesn't exist yet on a database that hasn't migrated
            logger.warning("Shows: %s", e)
            items = []
        if items and clusters_list:
            ids = [c['cluster'] for c in clusters_list]
            titles = [self.context['titles'][k] for k in ids]
            vectors = embed([i['title'] for i in items] + titles)
            vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
            similarity = vectors[:len(items)] @ vectors[len(items):].T
            for item, row in zip(items, similarity):
                best = int(row.argmax())
                item['story'] = int(ids[best]) if row[best] >= INVESTIGATION_MATCH else None
                item['story_title'] = titles[best] if item['story'] is not None else None
        for item in items:
            item.setdefault('story', None)
            item.setdefault('story_title', None)
            item['emoji'] = self.SHOW_KIND.get(item['kind'], '🎙️')
            item['color'] = self.SHOW_GROUP.get(item['group'], '#b8b8c8')
            item['date'] = pd.Timestamp(item['published']).tz_convert('US/Eastern').strftime('%b %-d')
        self.context['shows'] = items

    # A piece of an episode's title or description this close in meaning to a story covers it. Checked by hand on
    # Oct 3: above 0.55 the matches were right; below 0.5 mostly wrong
    SHOW_MATCH = 0.55
    PIECES = re.compile(r'\s*(?:[,;|•]|\s[&+]\s|\s-\s|:\s)\s*')

    def show_coverage(self, clusters_list):
        """Which current stories the news-of-the-day shows covered in the last few days, for a row on each story card.
        A rundown episode covers several stories ("Wages Vs Inflation, Tennessee Failed Execution, Cornell Rape
        Case"), so each item is split into pieces (its title on separators, and its description's first sentences)
        and every piece is matched to the stories on its own; one episode can land on several cards."""
        self.context['show_coverage'] = {}
        if not clusters_list:
            return
        try:
            items = sidefeeds.recent(days=3, limit=400, per_source=40)
        except Exception as e:  # noqa
            logger.warning("Show coverage: %s", e)
            return
        pieces, owner = [], []
        for n, item in enumerate(items):
            parts = [p for p in self.PIECES.split(item['title']) if len(p.split()) >= 2]
            parts += [p for p in re.split(r'(?<=[.!?])\s+', item['summary'])[:2] if len(p.split()) >= 4]
            for part in parts or [item['title']]:
                pieces.append(part)
                owner.append(n)
        if not pieces:
            return
        ids = [c['cluster'] for c in clusters_list]
        titles = [self.context['titles'][k] for k in ids]
        vectors = embed(pieces + titles)
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        similarity = vectors[:len(pieces)] @ vectors[len(pieces):].T
        covered = defaultdict(dict)  # cluster -> source -> newest item covering it
        for n, row in zip(owner, similarity):
            best = int(row.argmax())
            if row[best] < self.SHOW_MATCH:
                continue
            item = items[n]
            src = covered[ids[best]]
            if item['source'] not in src or item['published'] > src[item['source']]['published']:
                src[item['source']] = item
        for cluster, by_source in covered.items():
            chips = sorted(by_source.values(), key=lambda i: i['published'], reverse=True)[:4]
            self.context['show_coverage'][int(cluster)] = [
                {**i, 'emoji': self.SHOW_KIND.get(i['kind'], '🎙️'), 'color': self.SHOW_GROUP.get(i['group'], '#b8b8c8')}
                for i in chips]
        logger.info("Show coverage: %d items across %d stories", len(items), len(covered))

    def meter_trends(self, clusters_list):
        """Save this run's meters for every story, then mark the cards whose lean or mood has moved (#133)."""
        story_of = getattr(self, 'story_of', {})
        meters = {story_of[c['cluster']]: {'lean': c['lean']['value'], 'mood': c['mood']['value'],
                                           'outlets': c['outlets']}
                  for c in clusters_list if c['cluster'] in story_of}
        if not meters:
            return
        trends_meter.save(meters)
        moved = trends_meter.trends(list(meters))
        for c in clusters_list:
            trend = moved.get(story_of.get(c['cluster']))
            if trend:
                c['trend'] = trend

    def curators(self, df, clusters_list):
        """Which aggregators (Google News, Drudge…) are linking each story right now: an aggregator's live headline
        goes to the story holding the headline most like it, when that's CURATOR_MATCH or closer."""
        for c in clusters_list:
            c['curators'] = []
        curated = getattr(self, 'curated', None)
        members = df[df['cluster'] != -1]
        if curated is None or curated.empty or members.empty:
            return
        titles = curated['title'].tolist() + members['title'].tolist()
        vectors = embed(titles)
        vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
        similarity = vectors[:len(curated)] @ vectors[len(curated):].T
        by_cluster = {c['cluster']: c for c in clusters_list}
        clusters = members['cluster'].tolist()
        for agency, row in zip(curated['agency'], similarity):
            best = int(row.argmax())
            cluster = by_cluster.get(clusters[best])
            if row[best] >= CURATOR_MATCH and cluster is not None and agency not in cluster['curators']:
                cluster['curators'].append(agency)
        for c in clusters_list:
            c['curators'].sort()
        logger.info("Curators: %d of %d live aggregator headlines link a current story",
                    sum(len(c['curators']) for c in clusters_list), len(curated))

    def blindspots(self, clusters_list):
        """Stories covered almost entirely by one side: at least BLINDSPOT_MIN_OUTLETS rated outlets, BLINDSPOT_SHARE
        or more of them from one side, and that side's share at least BLINDSPOT_LIFT times its share of all the rated
        outlets in the pool (which itself leans left, so a mostly-left story is less unusual than a mostly-right one)."""
        pool = {a['agency']: a['bias'] for c in clusters_list for a in c['data'] if a['rated']}
        sides = {'left': sum(b < 0 for b in pool.values()) / max(1, len(pool)),
                 'right': sum(b > 0 for b in pool.values()) / max(1, len(pool))}
        found = {'left': [], 'right': []}
        for c in clusters_list:
            rated = {a['agency']: a['bias'] for a in c['data'] if a['rated']}
            if len(rated) < BLINDSPOT_MIN_OUTLETS:
                continue
            counts = {'left': sum(b < 0 for b in rated.values()), 'center': sum(b == 0 for b in rated.values()),
                      'right': sum(b > 0 for b in rated.values())}
            for side in ('left', 'right'):
                share = counts[side] / len(rated)
                if share >= BLINDSPOT_SHARE and share >= BLINDSPOT_LIFT * sides[side]:
                    found[side].append({'cluster': int(c['cluster']), 'title': self.context['titles'][c['cluster']],
                                        'share': round(100 * share), **counts})
                    c['blindspot'] = {'side': side, 'share': round(100 * share), **counts}  # for its story card
        for side in found:
            found[side].sort(key=lambda s: (-s['share'], -(s['left'] + s['right'] + s['center'])))
        # Where an average story would split, for the tick on each blindspot's meter
        found['pool'] = {'left': round(100 * sides['left']), 'center': round(100 * (1 - sides['left'] - sides['right'])),
                         'right': round(100 * sides['right'])}
        self.context['blindspots'] = found if found['left'] or found['right'] else None
        logger.info("Blindspots: %d mostly left, %d mostly right", len(found['left']), len(found['right']))

    def make_agency_lists(self, clusters_list):
        # Articles whose headline the outlet rewrote (minor changes excluded), to mark their chips and the stories
        # where many outlets are rewriting
        edits, _ = find_edits()
        rewritten = set(edits['url']) if not edits.empty else set()
        now = pd.Timestamp.now(tz='US/Eastern')
        agency_lists = {}
        for cluster in clusters_list:
            cluster['data'].sort(key=lambda x: x['agency'])
            hrefs = [f"<p>{len(cluster['data'])} headlines / {cluster['coverage']}% coverage</p>"]
            # The page's script keeps this current from data-first; the text here is for readers without javascript
            story_first_seen = min(a['appearance'] for a in cluster['data']).isoformat()
            minutes = cluster['first'] // 60
            if minutes < BREAKING_MINUTES:
                fallback = f'<h3>🚨🚨🚨BREAKING! {int(minutes)}m ago!</h3>'
            else:
                hours = int(cluster['first'] // 3600)
                fallback = f'<p>First seen {hours} hour{"" if hours == 1 else "s"} ago</p>'
            hrefs[-1] += f'<div class="broken" data-first="{story_first_seen}">{fallback}</div>'
            cluster['rewrites'] = sum(a['url'] in rewritten for a in cluster['data'])
            if cluster['rewrites'] >= max(CHURN_OUTLETS, CHURN_SHARE * len(cluster['data'])):
                hrefs[-1] += (f'<a class="churn" href="edits.html" title="Outlets are still changing how they headline'
                              f' this story">✏️ High headline churn: {cluster["rewrites"]} outlets changed theirs</a>')
            # Still-showing count and how long ago outlets first ran it
            live = sum(bool(a['live']) for a in cluster['data'])
            ages = sorted((now - a['first_seen']).total_seconds() / 3600 for a in cluster['data'])
            median_age = ages[len(ages) // 2]
            hrefs[-1] += (f'<p class="story-status">{live} of {len(cluster["data"])} outlets still showing it'
                          f' · typically first seen {age_text(median_age)} ago'
                          + (f' · <span class="fast-break">🚀 {cluster["speed"]} in the first hour</span>'
                             if (cluster.get('speed') or 0) >= FAST_BREAK else '') + '</p>')
            hrefs.append(SORT_BAR)
            chips = []
            for a in sorted(cluster['data'], key=lambda x: x['bias']):
                smiley = '😐' if a['sentiment'] == 0 else '😊' if a['sentiment'] > 0 else '😠'
                bias = a['bias'] + 3
                first_seen = a['appearance'].strftime(TOOLTIP_TIME)
                edited = a['url'] in rewritten
                hours_live = (now - a['first_seen']).total_seconds() / 3600
                hours_gone = (now - a['last_seen']).total_seconds() / 3600
                notes = []
                if edited:
                    notes.append('its headline for this article has changed since first seen')
                if a['live'] and hours_live < FRESH_HOURS:
                    state, badge, opacity = 'fresh', ' ✨', 1.0
                    notes.append(f'new on its front page in the last {FRESH_HOURS} hours')
                elif a['live']:
                    state, badge, opacity = 'live', '', 1.0
                else:
                    # Fades the longer it's been gone, down to a ghost
                    state, badge = 'gone', ' 👻'
                    opacity = max(GHOST_OPACITY, 1 - hours_gone / GHOST_FADE_HOURS)
                    notes.append(f'dropped off its front page {age_text(hours_gone)} ago')
                note = ''.join(f' · {n}' for n in notes)
                chips.append(
                    f'<a data-tooltip-color="{bias_colors[bias]}" data-tooltip-ink="{bias_ink[bias]}"'
                    f' class="storylink chip-{state}"'
                    f' style="{chip_style(a["agency"], a["bias"])}; opacity: {opacity:.2f}"'
                    f' data-bias="{a["bias"]}" data-first="{a["first_seen"].timestamp():.0f}"'
                    f' data-last="{a["last_seen"].timestamp():.0f}"'
                    f' data-live="{int(bool(a["live"]))}" data-mood="{a["sentiment"]:.3f}"'
                    f' data-framing="{a["deviation"]:.3f}"'
                    f' title="{a["title"]} (first seen {first_seen}) · {a["deviation"]:+.2f} vs. other outlets{note}"'
                    f' href="{a["url"]}">{outlet_icon(a["agency"])}{short_name(a["agency"])} {smiley}{" ✏️" if edited else ""}{badge}</a>'
                )
            hrefs.append(f'<div class="chips">{" ".join(chips)}</div>')
            agency_lists[cluster['cluster']] = ' '.join(hrefs)
        self.context['agency_lists'] = agency_lists

    def summarize(self, df, labels: dict[int, str]):
        summaries, titles = {}, {}
        for key, group in df.groupby('cluster'):
            if key in labels:
                summaries[key] = titles[key] = labels[key]
                continue
            # Without an llm label, fall back to the most centrist outlet's headline
            group['bias_abs'] = group['bias'].abs()
            center = group.loc[group['bias_abs'].idxmin()]
            summaries[key] = f'{center['agency']}: {center['title']}'
            titles[key] = center['title']
        self.context['summaries'] = summaries
        self.context['titles'] = titles

    def table_rows(self, df) -> list[dict]:
        """Every headline of the day for the table at the bottom of the page, newest first, with what we know
        about it: lean, mood, loaded wording, ranked feelings, and the story card it belongs to, if any. Only what's on
        a front page right now.

        Buzz is the old "xkeyscore" (calculate_xkeyscore): how many of the day's most common words and phrases a
        headline uses, i.e. how much it's on the same beat as everyone else. Shown as a percentile of the day's
        headlines, since the raw count grows with headline length and means little by itself."""
        stories = {a['url']: c['cluster'] for c in self.context.get('clusters', []) for a in c['data']}
        sizes = {c['cluster']: len(c['data']) for c in self.context.get('clusters', [])}
        summaries = self.context.get('summaries', {})
        df = df.assign(buzz=(100 * df['score'].rank(pct=True)).round().astype(int))
        df = df[df['live']]
        raw_seen = self.dh.main_headline_df.groupby('url')['first_accessed'].min()
        rows = []
        for r in df.sort_values('buzz', ascending=False).itertuples():
            ranks = r.emotion_ranks if isinstance(r.emotion_ranks, str) else ''
            topic = r.topic if isinstance(r.topic, str) else ''
            rows.append({
                'agency': r.agency, 'bias': int(r.bias), 'rated': bool(getattr(r, 'rated', True)), 'url': r.url, 'title': r.title.strip(),
                'seen': int(raw_seen[r.url].timestamp()) if r.url in raw_seen else None, 'buzz': int(r.buzz),
                'topic': topic, 'topic_url': f"{topic.replace(' ', '_')}.html" if topic else '',
                'mood': None if pd.isna(r.event_score) else int(r.event_score),
                'loaded': None if pd.isna(r.loaded_score) else int(r.loaded_score),
                'feelings': [[EMOTION_EMOJI[e], e] for e in ranks.split(',') if e in EMOTION_EMOJI and e != 'neutral'],
                'story': int(stories[r.url]) if r.url in stories else None,
                'story_title': summaries.get(stories[r.url], '') if r.url in stories else '',
                'story_size': sizes.get(stories[r.url], 0) if r.url in stories else 0,
            })
        return rows

    @staticmethod
    def filter_score_sort(df):
        # if windows:
        fa_str = '%b %-d %-I:%M %p'
        la_str = '%-I:%M %p'
        if os.name == 'nt':  # Windows doesn't like the whole dash thing.
            fa_str = fa_str.replace('-', '')
            la_str = la_str.replace('-', '')
        df['country'] = df['country'].map({c.value: c.name for c in list(Country)})
        # Score and sort while the times are still times; as display text, 9:41 AM would sort after 10:15 AM
        df = calculate_xkeyscore(df.copy())
        df['first_accessed'] = df['first_accessed'].dt.strftime(fa_str)
        df['last_accessed'] = df['last_accessed'].dt.strftime(la_str)
        return df


if __name__ == '__main__':
    Config.set_debug()
    from app.builder import prepare
    prepare()  # icons, ratings and lean estimates, as in a full build
    HeadlinesPage(DataHandler([DataTypes.headlines])).generate()
    copy_assets()
