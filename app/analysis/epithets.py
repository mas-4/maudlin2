"""Loaded labels (#150): contested vocabulary, the same thing named differently depending on who's talking ("illegal
alien" / "undocumented immigrant", "Biden judge", "MAGA"). A curated lexicon (epithets.csv) is counted in news
headlines by outlet and by side; a weekly mining of phrases one side uses far more than the other (log-odds with an
informative prior) suggests candidates for the lexicon, kept for review and never published on their own."""
import csv
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz

from app.models import Session, Headline, Article, Agency
from app.utils import Config, Constants, get_logger

logger = get_logger(__name__)

LEXICON = os.path.join(Constants.Paths.ROOT, 'epithets.csv')
CANDIDATES = os.path.join(Config.data, 'epithet_candidates.json')
WINDOW_DAYS = 30
MIN_OUTLETS = 3  # a mined phrase must come from this many outlets on its side
WORD = re.compile(r"[a-z][a-z'-]+")
STOP = set('the a an of to in on for and or with at by from as is are was be has have had will after over his her '
           'their its this that it he she they we you not but new says say said who what how why when more than '
           'about into up out us than'.split())


def lexicon() -> list[dict]:
    with open(LEXICON, newline='') as f:
        rows = list(csv.DictReader(line for line in f if not line.startswith('#')))
    for row in rows:
        row['regex'] = re.compile(row['pattern'], re.IGNORECASE)
    return rows


def side(bias: int, rated: bool) -> str:
    if not rated:
        return 'unrated'
    return 'left' if bias < 0 else 'right' if bias > 0 else 'center'


def headlines(days: int = WINDOW_DAYS) -> pd.DataFrame:
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    with Session() as s:
        rows = s.query(Headline.title, Headline.first_accessed, Article.url, Agency.name, Agency._bias,
                       Agency.lean_rated).join(Article, Article.id == Headline.article_id) \
            .join(Agency, Agency.id == Article.agency_id) \
            .filter(Headline.first_accessed >= since, (Headline.news_score.is_(None)) | (Headline.news_score >= 0.5)) \
            .all()
    df = pd.DataFrame(rows, columns=['title', 'first', 'url', 'agency', 'bias', 'rated'])
    if not df.empty:
        df['side'] = [side(int(b), bool(r)) for b, r in zip(df['bias'], df['rated'])]
    return df


def count(df: pd.DataFrame, terms: list[dict]) -> list[dict]:
    """Per family, per term: headlines using it, split by side, its top outlets and its newest example."""
    families = defaultdict(list)
    for term in terms:
        hits = df[df['title'].str.contains(term['regex'], na=False)]
        sides = hits['side'].value_counts().to_dict()
        newest = hits.sort_values('first').iloc[-1] if not hits.empty else None
        families[term['family']].append({
            'term': term['term'], 'note': term['note'], 'total': len(hits),
            'left': sides.get('left', 0), 'center': sides.get('center', 0), 'right': sides.get('right', 0),
            'unrated': sides.get('unrated', 0),
            'outlets': [{'name': a, 'n': int(n), 'bias': int(hits.loc[hits['agency'] == a, 'bias'].iloc[0])}
                        for a, n in hits['agency'].value_counts().head(4).items()],
            'example': {'title': newest['title'], 'url': newest['url'], 'agency': newest['agency']}
            if newest is not None else None,
        })
    return [{'family': name, 'terms': sorted(ts, key=lambda t: -t['total'])} for name, ts in families.items()
            if any(t['total'] for t in ts)]


def mine_candidates(df: pd.DataFrame, top: int = 40, min_count: int = 4) -> list[dict]:
    """Two- and three-word phrases one side uses far more than the other: the log-odds ratio with an informative
    Dirichlet prior (Monroe, Colaresi & Quinn 2008), as a z-score. Candidates for the lexicon, for a person to judge."""
    def grams(title):
        words = [w for w in WORD.findall(title.lower())]
        out = set()
        for n in (2, 3):
            for i in range(len(words) - n + 1):
                gram = words[i:i + n]
                if gram[0] not in STOP and gram[-1] not in STOP:
                    out.add(' '.join(gram))
        return out
    counts = {s: Counter() for s in ('left', 'right')}
    outlets = {s: defaultdict(set) for s in ('left', 'right')}
    names = {w for agency in df['agency'].unique() for w in WORD.findall(agency.lower())}
    for title, s, agency in zip(df['title'], df['side'], df['agency']):
        if s in counts:
            title = re.sub(r'\s+[-|]\s+[^-|]+$', '', title)  # Google News adds " - Outlet" to titles
            found = grams(title)
            counts[s].update(found)
            for gram in found:
                outlets[s][gram].add(agency)
    prior = counts['left'] + counts['right']
    n_l, n_r, a0 = sum(counts['left'].values()), sum(counts['right'].values()), sum(prior.values())
    out = []
    for gram, a in prior.items():
        if a < min_count:
            continue
        yl, yr = counts['left'][gram], counts['right'][gram]
        lead = 'left' if yl >= yr else 'right'
        # A house phrase (a byline, a series name, an outlet's name) isn't vocabulary: it must come from several
        # outlets on its side, and not be made of outlet names
        if len(outlets[lead][gram]) < MIN_OUTLETS or set(gram.split()) <= names:
            continue
        delta = math.log((yl + a) / (n_l + a0 - yl - a)) - math.log((yr + a) / (n_r + a0 - yr - a))
        z = delta / math.sqrt(1 / (yl + a) + 1 / (yr + a))
        out.append({'phrase': gram, 'z': round(z, 2), 'left': yl, 'right': yr})
    out.sort(key=lambda c: -abs(c['z']))
    return out[:top]


def build() -> dict:
    """Everything the labels page needs, and the week's candidates saved for review (left vs. right, and center
    outlets vs. everyone else, for the center's own house vocabulary)."""
    df = headlines()
    if df.empty:
        return {'families': [], 'headlines': 0}
    families = count(df, lexicon())
    week = df[df['first'] >= df['first'].max() - td(days=7)]
    candidates = mine_candidates(week)
    center = mine_candidates(week.assign(side=week['side'].map(
        lambda s: 'left' if s == 'center' else 'right' if s in ('left', 'right') else s)))
    center = [{**c, 'center': c.pop('left'), 'others': c.pop('right')} for c in center if c['z'] > 0]
    with open(CANDIDATES, 'w') as f:
        json.dump({'made': dt.now(pytz.UTC).isoformat(), 'left_vs_right': candidates, 'center_vs_rest': center},
                  f, indent=1)
    rated = df[df['side'] != 'unrated']
    pool = {s: round(100 * (rated['side'] == s).mean()) for s in ('left', 'center', 'right')} if len(rated) else {}
    logger.info("Loaded labels: %d families from %d headlines; top candidates: %s", len(families), len(df),
                ', '.join(c['phrase'] for c in candidates[:8]))
    return {'families': families, 'headlines': len(df), 'pool': pool, 'days': WINDOW_DAYS}
