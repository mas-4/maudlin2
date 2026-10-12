"""How newsy each hour was: the news-day score over time (Oct 12, the person: "some kind of chart somewhere on the site
that shows the newsiness score and a link to the story on spikes"). The score is the front page's news-day sticker
(page_headlines.news_day): for the story where it's highest, the share of the outlets with a story on their front page
now that carry it, at full weight for NEWS_DAY_FRESH_HOURS from its first sighting, then halving every
NEWS_DAY_HALF_LIFE_HOURS. 0.45 and up is a big news day, 0.25 a normal one.

    recorded       from Oct 12 each build keeps its own score and top story (record(), from news_day): exact
    reconstructed  before then, from the database: at each hourly run (the story snapshots' times) a headline counts
                   as on its front page if first seen by then and last seen no earlier than 25 minutes before; outlets
                   and stories as the build counts them (US outlets and the exempted British ones, no aggregators,
                   news headlines first seen in the last 3 days, only outlets with a headline in some story). Checked
                   against the build at Oct 12, 21:06 UTC: 53 outlets on the top story either way, 83 outlets in play
                   against the build's 81 (0.64 against 0.65). Sagas aren't joined here, so a saga's parts count apart

Kept in NEWSINESS (json): {'recorded': [points], 'reconstructed': [points]}; a point is {'at' (UTC), 'score', 'share',
'outlets', 'active', 'story' (id), 'label', 'kind'}."""
from datetime import datetime as dt, timedelta as td

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

NEWSINESS = f'{Config.data}/newsiness.json'
BIG, NORMAL = 0.45, 0.25  # page_headlines.NEWS_DAY_TIERS
LIVE_SLACK = td(minutes=25)  # models' last_accessed: a headline seen in the latest scrape
LOOKBACK = td(days=3)  # data.py: headlines first seen in the last 3 days


def kind_of(score: float) -> str:
    return 'big' if score >= BIG else 'normal' if score >= NORMAL else 'slow'


def load() -> dict:
    return read_json(NEWSINESS, {'recorded': [], 'reconstructed': []})


def record(newsday: dict, story_id: int | None, at: dt | None = None):
    """A build's own news-day score and top story, kept (page_headlines.news_day, outside debug)"""
    if not newsday or newsday.get('score') is None:
        return
    data = load()
    at = (at or dt.utcnow()).isoformat(timespec='seconds')
    data['recorded'].append({'at': at, 'score': newsday['score'], 'share': newsday['share'] / 100,
                             'outlets': newsday['outlets'], 'active': newsday['active'], 'story': story_id,
                             'label': newsday['story'], 'kind': newsday['kind']})
    write_json(NEWSINESS, data)


def reconstruct(until: dt | None = None) -> list[dict]:
    """The score at every hourly run with story snapshots before `until` (all of them if None), from the database"""
    import numpy as np
    import pandas as pd

    from app.models import Agency, Article, Headline, Session, Story, StoryHeadline, StorySnapshot
    from app.site.data import NEWS_ONLY
    from app.site.page_headlines import AGGREGATORS, NEWS_DAY_FRESH_HOURS, NEWS_DAY_HALF_LIFE_HOURS
    from app.utils.constants import Country
    with Session() as s:
        q = s.query(StorySnapshot.at).distinct().order_by(StorySnapshot.at)
        times = [t for (t,) in q if until is None or t < until]
        if not times:
            return []
        pool = {a.id for a in s.query(Agency) if a.name not in AGGREGATORS and (
            a._country == Country.us.value or (a._country == Country.gb.value and a.name in Config.exempted_foreign_media))}
        rows = s.query(Article.agency_id, Headline.first_accessed, Headline.last_accessed, StoryHeadline.story_id) \
            .join(Headline.article).join(StoryHeadline, StoryHeadline.headline_id == Headline.id) \
            .filter(Headline.last_accessed >= times[0] - LOOKBACK, NEWS_ONLY).all()
        stories = {i: (label or '', first) for i, label, first in s.query(Story.id, Story.label, Story.first_seen)}
    df = pd.DataFrame(rows, columns=['agency', 'first', 'last', 'story'])
    df = df[df['agency'].isin(pool)]
    out = []
    for t in times:
        live = df[(df['first'] <= t) & (df['first'] > t - LOOKBACK) & (df['last'] >= t - LIVE_SLACK)]
        active = live['agency'].nunique()
        per = live.groupby('story')['agency'].nunique()
        if per.empty or not active:
            continue
        hours = np.array([(t - stories[int(i)][1]).total_seconds() / 3600 if int(i) in stories else 0.0 for i in per.index])
        score = per.values / active * 0.5 ** (np.clip(hours - NEWS_DAY_FRESH_HOURS, 0, None) / NEWS_DAY_HALF_LIFE_HOURS)
        k = int(np.argmax(score))
        sid = int(per.index[k])
        out.append({'at': t.isoformat(timespec='seconds'), 'score': round(float(score[k]), 3),
                    'share': round(float(per.values[k] / active), 3), 'outlets': int(per.values[k]), 'active': int(active),
                    'story': sid, 'label': stories.get(sid, ('', None))[0], 'kind': kind_of(float(score[k]))})
    return out


def series() -> list[dict]:
    """Every point, oldest first: reconstructed before the first recorded build (worked out once and kept), recorded
    after; each marked with how it was made"""
    data = load()
    first = min((p['at'] for p in data['recorded']), default=None)
    if not data['reconstructed'] or (first is None and data['reconstructed'][-1]['at'] < (dt.utcnow() - td(hours=2)).isoformat()):
        data['reconstructed'] = reconstruct(dt.fromisoformat(first) if first else None)
        write_json(NEWSINESS, data)
    early = [{**p, 'made': 'reconstructed'} for p in data['reconstructed'] if first is None or p['at'] < first]
    return early + [{**p, 'made': 'recorded'} for p in data['recorded']]


def spikes(points: list[dict], line: float = BIG) -> list[dict]:
    """Each story's highest point where it made a big news day, oldest first"""
    best = {}
    for p in points:
        if p['score'] >= line and p.get('story') is not None and p['score'] > best.get(p['story'], {}).get('score', -1):
            best[p['story']] = p
    return sorted(best.values(), key=lambda p: p['at'])


# The first newsiness measure (May 2024, the person's own; dev/newsiness2.ipynb uses it): how many pairs of an hour's
# headlines say nearly the same thing, by TF-IDF likeness. Kept as it was.
def get_newsiness(headlines):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    import numpy as np
    tfidf = TfidfVectorizer(stop_words='english')
    cosim = cosine_similarity(tfidf.fit_transform(headlines))
    # Zero out the diagonal
    np.fill_diagonal(cosim, 0)
    # Zero out all values less than 0.5
    cosim[cosim < 0.5] = 0
    # Take the # of non-zero values divided by the total shape of the matrix
    return (np.count_nonzero(cosim) / cosim.size) * 10_000
