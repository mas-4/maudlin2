"""Our own lean estimate, for outlets AllSides doesn't rate. A ridge regression learns AllSides' ratings (-2 left to 2
right) from the words and phrases in each rated outlet's news headlines over the last WINDOW_DAYS, and predicts the
rest. Wording is the signal that held up: story choice and headline embeddings did worse in leave-one-out tests.

It's conservative on purpose. An estimate is published only when the model as a whole checks out (its leave-one-out
predictions rank the rated outlets in roughly the right order) and it's confident about the outlet (the prediction is
well off center). Estimates are marked as ours and kept out of every lean average."""
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytz
from scipy.stats import spearmanr
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sqlalchemy import or_

from app.analysis.newsfilter import NEWS_THRESHOLD
from app.models import Session, Headline, Article, Agency
from app.utils import get_logger

logger = get_logger(__name__)

WINDOW_DAYS = 30
MIN_HEADLINES = 20  # an outlet needs this many news headlines in the window to be scored
ALPHA = 0.3  # ridge strength, chosen by leave-one-out on the first day of data
MIN_RANK_AGREEMENT = 0.45  # the model's leave-one-out predictions must rank rated outlets at least this well
MIN_STRENGTH = 0.55  # and an outlet's prediction must be at least this far from center to publish


def estimate() -> dict:
    """Returns {'quality': {...}, 'estimates': {outlet: lean}} with estimates only for unrated outlets that pass."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=WINDOW_DAYS)
    with Session() as s:
        rows = s.query(Agency.name, Agency._bias, Agency.lean_rated, Headline.title).join(  # noqa prot attr
            Headline.article).join(Article.agency).filter(
            Headline.first_accessed > since,
            or_(Headline.news_score == None, Headline.news_score >= NEWS_THRESHOLD),  # noqa: E711
        ).all()
    df = pd.DataFrame(rows, columns=['agency', 'bias', 'rated', 'title'])
    counts = df.groupby('agency').size()
    df = df[df['agency'].isin(counts[counts >= MIN_HEADLINES].index)]
    outlets = df.groupby('agency').agg(bias=('bias', 'first'), rated=('rated', 'first'))
    rated = outlets['rated'].astype(bool).values
    if rated.sum() < 20 or (~rated).sum() == 0:
        return {'quality': None, 'estimates': {}}
    docs = df.groupby('agency')['title'].apply(' '.join).loc[outlets.index]
    X = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True, stop_words='english').fit_transform(docs)
    y = outlets['bias'].values[rated].astype(float)
    Xr = X[rated]

    # Leave-one-out: hide each rated outlet, predict it from the rest
    held_out = np.array([Ridge(alpha=ALPHA).fit(Xr[np.arange(len(y)) != i], np.delete(y, i)).predict(Xr[i])[0]
                         for i in range(len(y))])
    called = np.abs(held_out) >= MIN_STRENGTH
    quality = {
        'outlets': int(len(y)),
        'rank_agreement': round(float(spearmanr(held_out, y)[0]), 2),
        'within_one': round(float(np.mean(np.abs(np.clip(np.round(held_out), -2, 2) - y) <= 1)), 2),
        'side_right': round(float(np.mean(np.sign(held_out[called]) == np.sign(y[called]))), 2) if called.any() else None,
        'called': int(called.sum()),
    }
    estimates = {}
    if quality['rank_agreement'] >= MIN_RANK_AGREEMENT:
        model = Ridge(alpha=ALPHA).fit(Xr, y)
        for name, lean in zip(outlets.index[~rated], model.predict(X[~rated])):
            if abs(lean) >= MIN_STRENGTH:
                estimates[name] = int(np.clip(np.round(lean), -2, 2))
    logger.info("Lean estimate: rank agreement %.2f, side right %s of %d called; estimates %s",
                quality['rank_agreement'], quality['side_right'], quality['called'], estimates or 'none')
    return {'quality': quality, 'estimates': estimates}
