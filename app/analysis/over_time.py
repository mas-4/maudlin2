"""The news over time (Nov 5, the person: "some interesting visualizations of the news over time"): the series behind
the page of that name (app/site/page_over_time.py, drawn by static/over_time.js). Each takes plain rows and gives the
page's data, so it can be tested without the database; days are Eastern, from naive UTC times.

    days_between(first, last)           every Eastern day from one to the other, as 'YYYY-MM-DD'
    emotion_days(rows, days)            each day's share of the news headlines' feeling, by feeling
    emotion_spikes(series, tops)        the days a feeling ran furthest above its usual share, with the day's story
    motif_tides(entries, days)          claims filed under the motifs told most in any one week, day by day
    saga_lines(rows, sagas, days)       the biggest sagas' headlines, day by day
    newsiness_series(points, spikes)    the hourly news-day score and its labelled spikes
    cluster_labels(xy, groups)          where on the galaxy each big saga or story sits, if it sits together"""
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

import numpy as np
import pytz

from app.analysis.newsfilter import EMOTIONS, emotion_weights

EASTERN = pytz.timezone('US/Eastern')
FEELINGS = [e for e in EMOTIONS if e != 'neutral'] + ['neutral']  # the stack's order, no strong feeling on top
MIN_DAY_HEADLINES = 200  # a day with fewer news headlines (our first evening, a broken scrape) isn't drawn
SPIKES = 6  # emotion spikes labelled
PER_FEELING = 2  # of them, a feeling's highest days
TIDES = 12  # motifs in the tides
TIDE_WEEK = 7  # days in the window a motif's tide is ranked by
SAGAS = 12  # sagas on the lifelines


def local_day(t: datetime) -> str:
    """A naive UTC time's Eastern day"""
    return pytz.UTC.localize(t).astimezone(EASTERN).strftime('%Y-%m-%d')


def days_between(first: str, last: str) -> list[str]:
    d0, d1 = date.fromisoformat(first), date.fromisoformat(last)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def emotion_days(rows, days: list[str]) -> dict:
    """rows: (Eastern day, emotion ranks) for news headlines. Each day, each feeling's share of the day's vote (a
    headline's one vote split 3:2:1 across the feelings it names, newsfilter.emotion_weights): {feelings, shares:
    {feeling: [share a day, None on a day with fewer than MIN_DAY_HEADLINES]}, counts: [headlines a day]}"""
    at = {d: i for i, d in enumerate(days)}
    sums = np.zeros((len(days), len(FEELINGS)))
    counts = np.zeros(len(days), dtype=int)
    col = {e: j for j, e in enumerate(FEELINGS)}
    tally = Counter((d, r) for d, r in rows if d in at and r)
    for (d, ranks), n in tally.items():
        w = emotion_weights(ranks)
        if not w:
            continue
        counts[at[d]] += n
        for e, v in w.items():
            if e in col:
                sums[at[d], col[e]] += v * n
    shares = {}
    for e, j in col.items():
        shares[e] = [round(float(sums[i, j] / counts[i]), 4) if counts[i] >= MIN_DAY_HEADLINES else None
                     for i in range(len(days))]
    return {'feelings': FEELINGS, 'shares': shares, 'counts': counts.tolist()}


def emotion_spikes(series: dict, days: list[str], tops: dict, n: int = SPIKES) -> list[dict]:
    """The days each feeling (not neutral) ran furthest above its usual share (its median): each feeling's
    PER_FEELING highest days, at most one feeling a day, the n furthest above usual: [{day, feeling, share, usual,
    story (the day's top story among the headlines that feeling led), ...}], oldest first. tops: {(day, feeling):
    {'story', 'label', 'headlines'}}"""
    found = []
    for e in FEELINGS:
        if e == 'neutral':
            continue
        vals = [(i, v) for i, v in enumerate(series['shares'][e])
                if v is not None and series['counts'][i] >= MIN_DAY_HEADLINES]
        if len(vals) < 3:
            continue
        usual = float(np.median([v for _, v in vals]))
        if usual <= 0:
            continue
        for i, v in sorted(vals, key=lambda iv: -iv[1])[:PER_FEELING]:
            if v > usual:
                found.append({'day': days[i], 'feeling': e, 'share': v, 'usual': round(usual, 4), 'lift': v / usual})
    out, used = [], set()
    for s in sorted(found, key=lambda s: -s['lift']):
        if s['day'] in used:
            continue
        used.add(s['day'])
        top = tops.get((s['day'], s['feeling']))
        out.append({**s, 'lift': round(s['lift'], 2), **({'story': top['story'], 'label': top['label'],
                                                          'headlines': top['headlines']} if top else {})})
        if len(out) == n:
            break
    return sorted(out, key=lambda s: s['day'])


def top_stories(rows) -> dict:
    """rows: (Eastern day, the headline's leading feeling, story id, story label). The story with the most headlines
    each day for each leading feeling: {(day, feeling): {story, label, headlines}}"""
    count = Counter((d, e, s) for d, e, s, _ in rows if s is not None)
    labels = {s: label for _, _, s, label in rows if s is not None}
    best = {}
    for (d, e, s), k in count.items():
        if (d, e) not in best or (k, -s) > (best[d, e]['headlines'], -best[d, e]['story']):
            best[d, e] = {'story': s, 'label': labels.get(s) or '', 'headlines': k}
    return best


def daily(dates, days: list[str]) -> list[int]:
    """How many of `dates` ('YYYY-MM-DD...') fall on each of `days`"""
    at = {d: i for i, d in enumerate(days)}
    out = [0] * len(days)
    for d in dates:
        i = at.get((d or '')[:10])
        if i is not None:
            out[i] += 1
    return out


def peak(counts: list[int], days: list[str]) -> dict:
    """The day with the most (the first of equals)"""
    i = int(np.argmax(counts)) if counts else 0
    return {'day': days[i] if days else None, 'n': int(counts[i]) if counts else 0}


def best_week(counts: list[int], width: int = TIDE_WEEK) -> int:
    """The most in any `width` days running"""
    if not counts:
        return 0
    c = np.cumsum([0] + list(counts))
    w = min(width, len(counts))
    return int(max(c[i + w] - c[i] for i in range(len(counts) - w + 1)))


def motif_tides(entries: list[dict], days: list[str], top: int = TIDES) -> dict:
    """entries: the site's motifs (page_motifs.catalog: id, name, genre, claims with their dates). The motifs told most
    in any one week of `days`, each with its claims a day and its peak, the biggest week first; and every shown
    motif's claims a day added up: {motifs: [{id, name, genre, counts, total, week, peak}], all: [claims a day]}"""
    rows = []
    every = [0] * len(days)
    for e in entries:
        counts = daily([c.get('date', '') for c in e['claims']], days)
        every = [a + b for a, b in zip(every, counts)]
        total = sum(counts)
        if total:
            rows.append({'id': e['id'], 'name': e['name'], 'genre': e.get('genre', ''), 'counts': counts,
                         'total': total, 'week': best_week(counts), 'peak': peak(counts, days)})
    rows.sort(key=lambda r: (-r['week'], -r['total'], r['id']))
    return {'motifs': rows[:top], 'all': every}


def saga_lines(rows, sagas: dict, days: list[str], top: int = SAGAS) -> list[dict]:
    """rows: (saga id, Eastern day) a headline. sagas: {id: name}. The sagas with the most headlines, each with its
    headlines a day, its first and last day and its peak: [{id, name, counts, total, first, last, peak}], the
    earliest-starting first"""
    by = defaultdict(list)
    for g, d in rows:
        if g in sagas:
            by[g].append(d)
    out = []
    for g, ds in by.items():
        counts = daily(ds, days)
        total = sum(counts)
        if not total:
            continue
        on = [i for i, c in enumerate(counts) if c]
        out.append({'id': g, 'name': sagas[g], 'counts': counts, 'total': total, 'first': days[on[0]],
                    'last': days[on[-1]], 'peak': peak(counts, days)})
    out = sorted(out, key=lambda r: (-r['total'], r['id']))[:top]
    return sorted(out, key=lambda r: (r['first'], -r['total']))


def newsiness_series(points: list[dict], spikes: list[dict], link_of) -> dict:
    """The hourly news-day score (newsiness.series) for the page's chart: points as [time, score, kept by the build
    (1) or worked out afterwards (0), the top story's index, outlets, outlets in play], the stories' labels, and each
    spike above the big line with its link (link_of(point) -> href or None)"""
    stories, at = [], {}
    pts = []
    for p in points:
        key = (p.get('story'), p.get('label') or '')
        if key not in at:
            at[key] = len(stories)
            stories.append(p.get('label') or '')
        pts.append([p['at'], round(float(p['score']), 3), int(p.get('made') == 'recorded'), at[key],
                    int(p.get('outlets') or 0), int(p.get('active') or 0)])
    return {'points': pts, 'stories': stories,
            'spikes': [{'at': p['at'], 'score': round(float(p['score']), 3), 'label': p.get('label') or '',
                        'outlets': p.get('outlets'), 'active': p.get('active'), 'href': link_of(p)} for p in spikes]}


LABEL_LEAST = 120  # headlines a saga or story needs for a label on the galaxy
LABEL_NEAR = 0.05  # of the map's width: a label's group must have...
LABEL_SHARE = 0.4  # ...this share of its headlines within that distance of its middle
LABELS = 40


def cluster_labels(xy: np.ndarray, groups: dict, day: np.ndarray, least: int = LABEL_LEAST, most: int = LABELS) -> list[dict]:
    """groups: {key: {'name', 'href', 'rows': [row indexes into xy]}}; day: each row's day (its index). Where each big
    group sits on the galaxy (the median of its headlines' places), for the groups that sit together (LABEL_SHARE of
    them near that middle), the biggest first: [{name, href, x, y, n, days: [its first day, its last]}]"""
    out = []
    for g in groups.values():
        rows = np.asarray(g['rows'], dtype=int)
        if len(rows) < least:
            continue
        P = xy[rows]
        mid = np.median(P, axis=0)
        near = float(np.mean(np.linalg.norm(P - mid, axis=1) <= LABEL_NEAR))
        if near >= LABEL_SHARE:
            out.append({'name': g['name'], 'href': g.get('href'), 'x': round(float(mid[0]), 4),
                        'y': round(float(mid[1]), 4), 'n': len(rows),
                        'days': [int(day[rows].min()), int(day[rows].max())]})
    return sorted(out, key=lambda r: -r['n'])[:most]
