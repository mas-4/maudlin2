"""Wire share (#152): how much of each outlet's front page is AP or Reuters copy. A headline counts as wire copy when
it's nearly word for word a wire headline from the same week: sharing most of its words (WIRE_WORDS) and very close
in meaning (embedding cosine WIRE_MATCH, for the model that embedded them). Ten outlets running one AP headline aren't ten independent choices, and
the outlets page says how often each outlet does it."""
import re
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytz

from app.analysis.clustering import headline_vectors
from app.models import Session, Headline, Article, Agency
from app.utils import get_logger

logger = get_logger(__name__)

WIRES = {'AP', 'Reuters'}
WINDOW_DAYS = 7
WIRE_WORDS = 0.7  # share of words in common (Jaccard), so a rewrite of the wire story doesn't count
# And cosine for "nearly the same headline", per model. Oct 5: of 339 pairs with 0.7 of their words in common (a week),
# all copies, potion-base-8M at 0.9 kept 258 and mxbai at 0.85 all 339 (methods log)
WIRE_MATCH = {'mxbai-embed-large': 0.85, 'potion-base-8M': 0.9}
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
    wire_rows = np.flatnonzero(is_wire.to_numpy())
    other_rows = np.flatnonzero(~is_wire.to_numpy())
    # The word rule first, over every pair at once (words shared / words in either, by sparse word counts), then
    # meaning, for the pairs left
    from sklearn.feature_extraction.text import CountVectorizer
    counts = CountVectorizer(analyzer=lambda t: list(_words(t)), binary=True).fit(titles)
    W, O = counts.transform([titles[i] for i in wire_rows]), counts.transform([titles[i] for i in other_rows])
    nw, no = np.asarray(W.sum(axis=1)).ravel(), np.asarray(O.sum(axis=1)).ravel()
    shared = (O @ W.T).tocoo()
    pairs = [(other_rows[i], wire_rows[j]) for i, j, k in zip(shared.row, shared.col, shared.data)
             if k / (no[i] + nw[j] - k) >= WIRE_WORDS]
    if not pairs:
        return out
    rows = sorted({i for pair in pairs for i in pair})
    vectors, model = headline_vectors([titles[i] for i in rows])
    at = {i: k for k, i in enumerate(rows)}
    for r, w in pairs:
        if not out.iloc[r] and float(vectors[at[r]] @ vectors[at[w]]) >= WIRE_MATCH[model]:
            out.iloc[r] = True
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
