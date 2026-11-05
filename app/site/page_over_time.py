"""The news over time (over-time.html; Nov 5, the person: "can we do some interesting visualizations of the news over
time?"): our whole record at once. The headline galaxy (every headline we've read, placed by what it says:
app/analysis/galaxy.py), how newsy each hour was (app/analysis/newsiness.py), the motifs' tides, the feelings the news
stirred day by day, and the biggest sagas' lifelines; the series are worked out in app/analysis/over_time.py and drawn
by static/over_time.js.

The galaxy's points ride in a file of their own (galaxy/points.bin: 7 bytes a headline) and its headlines' words in
files of CHUNK headlines each (galaxy/t-N.json), fetched only when someone points at a dot; headlines keep their place in
id order, so only the newest file changes from one build to the next."""
import json
import os
import time
from datetime import UTC, datetime as dt, timedelta as td

import numpy as np

from app.analysis import galaxy, over_time as ot
from app.analysis.newsfilter import EMOTION_EMOJI, NEWS_THRESHOLD
from app.site.common import TemplateHandler, motif_href
from app.utils import Config, get_logger

logger = get_logger(__name__)

FOLDER = 'galaxy'  # in the build
CHUNK = 1000  # headlines a words file
TITLE_CHARS = 200
# The feelings' colors: the emotions page's board banners (page_emotions.PAIRS)
FEELING_INK = {'fear': '#8a5cff', 'anger': '#ff6b1a', 'sadness': '#8a8f98', 'disgust': '#7a8a00', 'surprise': '#ff4fa3',
               'joy': '#ffc400', 'hope': '#00c2a8', 'neutral': '#e2e2ea'}
# The galaxy's topics, brightest pops first, checked for color-blind pairs (dataviz validate_palette, on the night sky)
TOPIC_INK = ['#ff4fa3', '#ffc400', '#3a86ff', '#ff6b1a', '#00c2a8', '#b197fc', '#ff8787', '#8ce99a']


def utc_now() -> dt:
    return dt.now(UTC).replace(tzinfo=None)  # naive UTC, as the database keeps times


def headlines() -> list[tuple]:
    """Every headline in id order: (id, title, first seen, outlet, news score, emotion ranks, story id, story label,
    saga id)"""
    from app.models import Agency, Article, Headline, Session, Story, StoryHeadline
    with Session() as s:
        return s.query(Headline.id, Headline.title, Headline.first_accessed, Agency.name, Headline.news_score,
                       Headline.emotion_ranks, StoryHeadline.story_id, Story.label, Story.saga_id) \
            .join(Article, Article.id == Headline.article_id).join(Agency, Agency.id == Article.agency_id) \
            .outerjoin(StoryHeadline, StoryHeadline.headline_id == Headline.id) \
            .outerjoin(Story, Story.id == StoryHeadline.story_id).order_by(Headline.id).all()


def saga_names() -> dict[int, str]:
    """The sagas with a page (two parts or more, as sagas.history keeps them), by id: their names"""
    from sqlalchemy import func
    from app.models import Saga, Session, Story
    with Session() as s:
        parts = dict(s.query(Story.saga_id, func.count(Story.id)).filter(Story.saga_id.isnot(None)).group_by(Story.saga_id))
        return {g.id: g.name or f'Saga {g.id}' for g in s.query(Saga) if parts.get(g.id, 0) >= 2}


def story_pages() -> set[int]:
    """The stories with a page of their own: kept ones, and those seen in the last week (page_story.recent_stories)"""
    from app.models import Session, Story
    from app.site import page_story
    since = utc_now() - td(days=page_story.DAYS)
    with Session() as s:
        recent = {i for (i,) in s.query(Story.id).filter(Story.last_seen >= since)}
    return recent | page_story.archived_ids()


def short_day(day: str) -> str:
    return dt.strptime(day, '%Y-%m-%d').strftime('%b %-d')


def write_galaxy(rows: list[tuple], days: list[str], local: list[str], with_page: set[int], sagas: dict) -> dict | None:
    """The galaxy's files in the build and the page's part of it: topics, labels, counts"""
    from app.site import page_saga, page_story
    ids = np.array([r[0] for r in rows], dtype=np.int64)
    lay = galaxy.today(ids, [r[1] for r in rows])
    if not len(ids) or not len(lay['names']):
        return None
    folder = os.path.join(Config.build, FOLDER)
    os.makedirs(folder, exist_ok=True)
    at = {d: i for i, d in enumerate(days)}
    q = np.round(lay['xy'] * 65535).astype('<u2')
    day = np.array([at.get(d, 0) for d in local], dtype='<u2')
    blob = q[:, 0].tobytes() + q[:, 1].tobytes() + day.tobytes() + lay['topic'].astype(np.uint8).tobytes()
    with open(os.path.join(folder, 'points.bin'), 'wb') as f:
        f.write(blob)
    for k in range(0, len(rows), CHUNK):
        part = [[r[1].strip()[:TITLE_CHARS], r[3], short_day(d), r[7] or '',
                 page_story.page_name(r[6]) if r[6] in with_page else '']
                for r, d in zip(rows[k:k + CHUNK], local[k:k + CHUNK])]
        with open(os.path.join(folder, f't-{k // CHUNK}.json'), 'w', encoding='utf-8') as f:
            json.dump(part, f, ensure_ascii=False, separators=(',', ':'))
    groups = {}
    for n, r in enumerate(rows):
        story, label, saga = r[6], r[7], r[8]
        if saga in sagas:
            groups.setdefault(('saga', saga), {'name': '🧵 ' + sagas[saga], 'href': page_saga.page_name(saga),
                                               'rows': []})['rows'].append(n)
        elif story is not None and label:
            groups.setdefault(('story', story), {'name': label, 'href': page_story.page_name(story) if story in with_page
                                                 else None, 'rows': []})['rows'].append(n)
    topics = np.bincount(lay['topic'], minlength=len(lay['names']))
    return {'n': len(ids), 'chunk': CHUNK, 'stamp': f'{len(ids)}-{int(ids[-1])}-{lay["made"]}',
            'made': lay['made'], 'labels': ot.cluster_labels(lay['xy'], groups, day),
            'topics': [{'name': str(name), 'ink': TOPIC_INK[i % len(TOPIC_INK)], 'n': int(topics[i])}
                       for i, name in enumerate(lay['names'])], 'bytes': len(blob)}


def emotions(rows: list[tuple], local: list[str], days: list[str], with_page: set[int]) -> dict:
    news = [(d, r[5], r[6], r[7]) for r, d in zip(rows, local)
            if r[5] and r[4] is not None and r[4] >= NEWS_THRESHOLD]
    series = ot.emotion_days([(d, ranks) for d, ranks, _, _ in news], days)
    tops = ot.top_stories([(d, ranks.split(',')[0], s, label) for d, ranks, s, label in news])
    spikes = ot.emotion_spikes(series, days, tops)
    from app.site import page_story
    for s in spikes:
        s['emoji'] = EMOTION_EMOJI[s['feeling']]
        s['href'] = page_story.page_name(s['story']) if s.get('story') in with_page else None
    return {**series, 'spikes': spikes, 'ink': FEELING_INK, 'emoji': EMOTION_EMOJI}


def tides(days: list[str]) -> dict:
    from app.site.boards import GENRE_INK
    from app.site.page_motif import shared
    shown = shared()['catalog']  # the build's own, worked out once for the motif pages
    out = ot.motif_tides(shown['entries'], days)
    for m in out['motifs']:
        m['href'] = motif_href(m['id'])
        m['ink'] = GENRE_INK.get(m['genre'], '#ffffff')
        m['emoji'] = shown['genre_emoji'].get(m['genre'], '🧩')
    out['claims'] = sum(out['all'])
    out['motif_count'] = len(shown['entries'])
    return out


def newsiness(with_page: set[int], start: str) -> dict:
    from app.analysis import newsiness as nw
    from app.site import archive, page_story
    points = [p for p in nw.series() if ot.local_day(dt.fromisoformat(p['at'])) >= start]
    spikes = nw.spikes(points)
    published = set(archive._days())

    def link_of(p):  # as the archive's chart links them: the story's page, else that day's front page
        if p['story'] in with_page:
            return page_story.page_name(p['story'])
        day = ot.local_day(dt.fromisoformat(p['at']))
        if day == archive._today():
            return f"index.html#s-{p['story']}"
        return f"/{day.replace('-', '/')}/#s-{p['story']}" if day in published else None
    return {**ot.newsiness_series(points, spikes, link_of), 'big': nw.BIG, 'normal': nw.NORMAL}


def lifelines(rows: list[tuple], local: list[str], days: list[str], sagas: dict) -> list[dict]:
    from app.site import page_saga
    from app.site.page_headlines import SAGA_COLORS
    out = ot.saga_lines([(r[8], d) for r, d in zip(rows, local) if r[8] is not None], sagas, days)
    for s in out:
        s['href'] = page_saga.page_name(s['id'])
        s['ink'] = SAGA_COLORS[s['id'] % len(SAGA_COLORS)]  # its color on the front page and the saga tracker
    return out


class OverTimePage:
    def __init__(self, dh=None):
        self.template = TemplateHandler('over_time.html', 'over-time.html')
        self.context = {'title': 'The news over time',
                        'og_description': 'Every headline we have read, on one map, and how newsy each hour was, '
                                          'which stories people told and what the news made us feel, day by day.'}

    def generate(self):
        logger.info("Generating the news over time page...")
        t0 = time.time()
        rows = headlines()
        if not rows:
            logger.warning("News over time: no headlines, page not written")
            return
        local = [ot.local_day(r[2]) for r in rows]
        days = ot.days_between(min(local), max(max(local), ot.local_day(utc_now())))
        with_page, sagas = story_pages(), saga_names()
        data = {'days': days, 'today': ot.local_day(utc_now())}
        timings = {}
        for name, make in (('galaxy', lambda: write_galaxy(rows, days, local, with_page, sagas)),
                           ('newsiness', lambda: newsiness(with_page, days[0])),
                           ('tides', lambda: tides(days)),
                           ('emotions', lambda: emotions(rows, local, days, with_page)),
                           ('sagas', lambda: lifelines(rows, local, days, sagas))):
            t = time.time()
            try:
                data[name] = make()
            except Exception as e:  # noqa: BLE001 - the page stands without one of its charts
                logger.warning("News over time: %s failed (%s: %s)", name, type(e).__name__, e)
                data[name] = None
            timings[name] = round(time.time() - t, 1)
        self.context.update({'data': data, 'headlines': len(rows), 'start': short_day(days[0]),
                             'galaxy': data.get('galaxy'), 'tides': data.get('tides')})
        self.template.write(self.context)
        logger.info("...done in %.1f s (%s)", time.time() - t0, ', '.join(f'{k} {v} s' for k, v in timings.items()))



if __name__ == '__main__':
    # This page alone, into the build folder, for a local look (`MAUDLIN_DATA=<a copy> python -m app.site.page_over_time`)
    from app.site.common import copy_assets
    Config.set_debug()
    OverTimePage().generate()
    copy_assets()
