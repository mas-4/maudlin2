"""Wire share (#152): how much of each outlet's front page is AP or Reuters copy. A headline counts as wire copy when
it's nearly word for word a wire headline from the same week: very close in meaning (embedding cosine WIRE_MATCH)
and sharing most of its words (WIRE_WORDS). Ten outlets running one AP headline aren't ten independent choices, and
the outlets page says how often each outlet does it."""
import re
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytz

from app.analysis.clustering import embed
from app.models import Session, Headline, Article, Agency
from app.utils import get_logger

logger = get_logger(__name__)

WIRES = {'AP', 'Reuters'}
WINDOW_DAYS = 7
WIRE_MATCH = 0.9  # embedding cosine for "nearly the same headline" (checked by hand on Oct 4)
WIRE_WORDS = 0.7  # and this share of words in common (Jaccard), so a rewrite of the wire story doesn't count
MIN_HEADLINES = 10
WORD = re.compile(r"[\w$%'’]+")


def _words(title: str) -> set[str]:
    return {w.lower().replace('’', "'") for w in WORD.findall(title)}


def wire_copies(df: pd.DataFrame) -> pd.Series:
    """For a frame of headlines ('title', 'agency'), a boolean Series: is each non-wire headline wire copy?"""
    is_wire = df['agency'].isin(WIRES)
    out = pd.Series(False, index=df.index)
    if not is_wire.any() or is_wire.all():
        return out
    titles = df['title'].str.strip().tolist()
    vectors = embed(titles)
    vectors = vectors / np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-9)  # empty titles embed to 0
    wire_rows = np.flatnonzero(is_wire.to_numpy())
    other_rows = np.flatnonzero(~is_wire.to_numpy())
    wire_words = [_words(titles[i]) for i in wire_rows]
    for start in range(0, len(other_rows), 2000):  # in chunks, to keep the similarity matrix small
        rows = other_rows[start:start + 2000]
        similarity = vectors[rows] @ vectors[wire_rows].T
        for r, sims in zip(rows, similarity):
            words = _words(titles[r])
            for j in np.flatnonzero(sims >= WIRE_MATCH):
                union = words | wire_words[j]
                if union and len(words & wire_words[j]) / len(union) >= WIRE_WORDS:
                    out.iloc[r] = True
                    break
    return out


def wire_share(days: int = WINDOW_DAYS) -> pd.DataFrame:
    """Per outlet with MIN_HEADLINES or more news headlines in the window: headlines, wire copies and their share."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    with Session() as s:
        rows = s.query(Headline.title, Agency.name).join(Article, Article.id == Headline.article_id) \
            .join(Agency, Agency.id == Article.agency_id) \
            .filter(Headline.first_accessed >= since, (Headline.news_score.is_(None)) | (Headline.news_score >= 0.5)) \
            .all()
    df = pd.DataFrame(rows, columns=['title', 'agency'])
    if df.empty:
        return pd.DataFrame(columns=['headlines', 'wire', 'share'])
    df['wire'] = wire_copies(df)
    out = df[~df['agency'].isin(WIRES)].groupby('agency').agg(headlines=('title', 'size'), wire=('wire', 'sum'))
    out = out[out['headlines'] >= MIN_HEADLINES]
    out['share'] = out['wire'] / out['headlines']
    logger.info("Wire share: %d outlets; highest %s", len(out),
                ', '.join(f'{a} {s:.0%}' for a, s in out['share'].sort_values(ascending=False).head(5).items()))
    return out
