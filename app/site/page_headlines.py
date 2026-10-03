import os
import re
from datetime import datetime as dt

import numpy as np

from app.analysis.clustering import prepare_embedding_cosine, form_clusters, label_clusters, embed
from app.analysis.newsiness import get_newsiness
from app.analysis.stories import sync_stories, label_stories, headline_sentiment
from app.analysis import textnorm
from app.analysis.pipelines import Pipelines, prepare
from app.site.common import calculate_xkeyscore, copy_assets, TemplateHandler
from app.site.data import DataHandler, DataTypes
from app.analysis.edits import find_edits
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


def _name(text: str) -> str:
    """A trend's name for exact matching: no parenthetical, hyphens as spaces, lowercase."""
    return re.sub(r'\s+', ' ', re.sub(r'\(.*?\)', '', text).replace('-', ' ')).strip().lower()


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


class HeadlinesPage:
    def __init__(self, dh: DataHandler):
        self.dh = dh
        self.template = TemplateHandler('headlines.html', 'index.html')
        self.newsletter = TemplateHandler('newsletter.html')
        self.context = {'title': 'Current Headlines', 'breaking_minutes': BREAKING_MINUTES}

    def generate(self):
        logger.info("Generating headlines page...")
        df = self.filter_score_sort(self.dh.main_headline_df.copy())
        self.analyze_newsiness(self.dh.main_headline_df.copy())
        self.cluster_and_summarize(df.copy())
        table_df = self.process_headlines(df)
        # drop all rows with nan
        table_df.dropna(inplace=True)
        self.context['tabledata'] = table_df.values.tolist()
        self.newsletter.write(self.context)
        self.template.write(self.context)
        logger.info("...done")

    def analyze_newsiness(self, df):
        # Filter df for us or exempted foreign media
        df = df[(df['country'] == Country.us.value) | (df['agency'].isin(Config.exempted_foreign_media))]
        newsiness = get_newsiness(df['title'].tolist())
        # Floor the current time to the previous half hour
        halfhour = dt.now().replace(minute=30 if dt.now().minute >= 30 else 0, second=0, microsecond=0)
        halfhour = halfhour.hour * 60 + halfhour.minute
        weekday = dt.today().strftime("%A")
        ndf = self.dh.newsiness_df
        condition = (ndf['halfhour'] == halfhour) & (ndf['day'] == weekday)
        try:
            std = ndf[condition]['std'].values[0]
            mean = ndf[condition]['mean'].values[0]
            zscore = (newsiness - mean) / std

            if zscore > 1.5:
                slowday = f'<h1 class="busy newsday">🚨🗞️🚨 BIG NEWS DAY! 🚨🗞️🚨</h1>'
            elif zscore < 0.25:
                slowday = f'<h1 class="slow newsday">🌴🐢🍹 slow news day... 🍹🐢🌴</h1>'
            else:
                slowday = f'<h1 class="average newsday">📰🥸📰 Just Another Day of News. 📰🥸📰</h1>'
            slowday += f'<h3 style="text-align: center;">Newsiness score: {newsiness:.2f} (z-score: {zscore:.2f})</h3>'
        except IndexError:
            logger.warning("IndexError in analyze_newsiness, hour %i weekday %s", halfhour, weekday)
            slowday = '<h1 class="newsday">No idea how busy today is in the news. 🤷🤷🤷 (system error 🤖🔥🤖)</h1>'

        self.context['slowday'] = slowday

    def cluster_and_summarize(self, df):
        n_samples_per_cluster = 6
        threshold = 0.7  # embedding cosine; tuned against a day of headlines
        df = df[
            (df['country'] == Country.us.name)
            |
            (
                    (df['country'] == Country.gb.name)
                    &
                    (df['agency'].isin(Config.exempted_foreign_media))
            )
            ].copy()
        df['processed'] = df['title'].apply(lambda x: prepare(x, pipeline))

        # Partisan lean is measured against the outlets in today's pool, which lean one way themselves
        baseline_bias = df.drop_duplicates('agency')['bias'].mean()
        logger.info("Clustering %i headlines", len(df))
        df = df.reset_index(drop=True)  # cluster ids are positional
        clusters = form_clusters(prepare_embedding_cosine(df['title']), n_samples_per_cluster, threshold)
        logger.info("%i clusters formed", len(clusters))

        df = label_clusters(df, clusters)
        df = df[df['cluster'] != -1].copy()
        df.drop_duplicates(subset=['cluster', 'agency'], keep='first', inplace=True)
        df['text_length'] = df['title'].str.len()
        df = df.groupby('cluster').filter(lambda x: len(x) >= n_samples_per_cluster)
        logger.info("%i clusters left after filtering", df['cluster'].nunique())
        sentiment = df['sentiment'] = headline_sentiment(df)
        df['deviation'] = sentiment - sentiment.groupby(df['cluster']).transform('mean')
        stories = sync_stories(df)
        self.summarize(df, label_stories(df, stories))
        grouped = df.groupby('cluster')
        clusters_list = [{'cluster': key, 'data': group.to_dict(orient='records')} for key, group in grouped]
        for cluster in clusters_list:
            cluster['coverage'] = round(len(cluster['data']) / len(Scrapers) * 100, 2)
            cluster['first'] = max(cluster['data'], key=lambda x: x['howlong'])['howlong']
            group = df[df['cluster'] == cluster['cluster']]
            cluster['lean'] = meter(group['bias'].mean() - baseline_bias, LEAN_RANGE, 'L', 'R')
            cluster['mood'] = meter(headline_sentiment(group).mean(), MOOD_RANGE, '', '')

        # clusters_list.sort(key=lambda x: len(x['data']), reverse=True)
        clusters_list.sort(key=lambda x: x['first'])
        self.make_agency_lists(clusters_list)
        self.context['clusters'] = clusters_list
        self.trending_in_the_news(df)

    def trending_in_the_news(self, df):
        """Our own trending list, ranked by how many outlets carry each story, next to what's trending on social
        media, search and Wikipedia. Where a trend and a story are about the same thing both get marked, so the
        overlap (and the gap) between what the press covers and what people pay attention to is visible."""
        outlets = df.groupby('cluster')['agency'].nunique().sort_values(ascending=False)
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
        self.context['news_trends'] = [
            {'cluster': cluster, 'title': self.context['titles'][cluster], 'outlets': int(count),
             'also_on': sorted(set(on.get(cluster, [])))}
            for cluster, count in outlets.head(TRENDING_COUNT).items()
        ]

    def make_agency_lists(self, clusters_list):
        # Articles whose headline the outlet rewrote (minor changes excluded), to mark their chips and the stories
        # where many outlets are rewriting
        edits, _ = find_edits()
        rewritten = set(edits['url']) if not edits.empty else set()
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
            last_bias = -3
            for a in sorted(cluster['data'], key=lambda x: x['bias']):
                if a['bias'] != last_bias:
                    hrefs.append(f'<br>')
                    last_bias = a['bias']
                smiley = '😐' if a['sentiment'] == 0 else '😊' if a['sentiment'] > 0 else '😠'
                bias = a['bias'] + 3
                first_seen = a['appearance'].strftime(TOOLTIP_TIME)
                edited = a['url'] in rewritten
                note = ' · its headline for this article has changed since first seen' if edited else ''
                hrefs.append(
                    f'<a data-tooltip-color="{bias_colors[bias]}" data-tooltip-ink="{bias_ink[bias]}" class="storylink"'
                    f' style="background-color: {bias_colors[bias]}; color: {bias_ink[bias]}"'
                    f' title="{a["title"]} (first seen {first_seen}) · {a["deviation"]:+.2f} vs. other outlets{note}"'
                    f' href="{a["url"]}">{a["agency"]} {smiley}{" ✏️" if edited else ""}</a>'
                )
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

    @staticmethod
    def process_headlines(df):
        def format_title(x):
            t = x.title.replace("'", "").replace('"', '')
            t_trunc = t[:Config.headline_cutoff] + '...' if len(t) > Config.headline_cutoff else t
            return f'<a data-tooltip-color="#c4dbff" title="{t}" href="{x.url}">{x.agency} - {t_trunc}</a>'

        df['title'] = df.apply(format_title, axis=1)

        def format_topic(x):
            # Truncate headline_df['title'] to 255 characters and append a ... if it is longer
            if not x.topic:
                return ''
            topic_file = x.topic.replace(' ', '_') + '.html'
            return f'<a href="{topic_file}.html">{x.topic}</a>'

        df['topic'] = df.apply(format_topic, axis=1)
        df = df[['title', 'first_accessed', 'score', 'topic', 'vader_compound', 'afinn']]
        df = df.copy().sort_values(by='first_accessed', ascending=False)
        return df

    @staticmethod
    def filter_score_sort(df):
        # if windows:
        fa_str = '%b %-d %-I:%M %p'
        la_str = '%-I:%M %p'
        if os.name == 'nt':  # Windows doesn't like the whole dash thing.
            fa_str = fa_str.replace('-', '')
            la_str = la_str.replace('-', '')
        df['country'] = df['country'].map({c.value: c.name for c in list(Country)})
        df['first_accessed'] = df['first_accessed'].dt.strftime(fa_str)
        df['last_accessed'] = df['last_accessed'].dt.strftime(la_str)
        return calculate_xkeyscore(df.copy())


if __name__ == '__main__':
    Config.set_debug()
    HeadlinesPage(DataHandler([DataTypes.headlines])).generate()
    copy_assets()
