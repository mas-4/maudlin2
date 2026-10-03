"""Separates news headlines from everything else outlets put on their front pages: recipes, shopping deals,
evergreen how-tos, and page furniture that slips past the scraper filters.

When an llm is available it labels each new headline at scrape time (one headline per request: small models lose
track of numbered batches). `--label-headlines` builds a labeled sample and `--train-newsfilter` fits a small
embedding classifier on it as a fallback for when no llm is running. That classifier is much weaker than the llm,
so it uses a cutoff chosen to almost never drop real news."""
import os
import random
import time
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import update

from app.analysis.clustering import embed, EMBEDDING_MODEL
from app.analysis import llm
from app.utils import Config, get_logger

logger = get_logger(__name__)

LABELS_FILE = os.path.join(Config.data, 'headline_labels.csv')
MODEL_FILE = os.path.join(Config.data, 'newsfilter.joblib')
NEWS_THRESHOLD = 0.5
# The fallback classifier only drops a headline when it's at least this likely to be right
FALLBACK_PRECISION = 0.9

LABEL_PROMPT = """Classify this item scraped from {agency}'s front page.

- news: reporting, analysis or opinion about current events (politics, world, business, science, crime, \
courts, health, sports results, notable people and what happened to them)
- non_news: service and lifestyle content (recipes, shopping and deals, product reviews, travel guides, \
horoscopes, quizzes, evergreen how-to and advice)
- junk: not a headline at all (navigation, section names, bylines, promos, newsletter signups, template text)

Item: {title}"""

SCHEMA = {
    "type": "object",
    "properties": {"label": {"type": "string", "enum": ["news", "non_news", "junk"]}},
    "required": ["label"],
    "additionalProperties": False,
}

# One headline per request: asked to label a numbered batch, small models lose track of which label belongs to
# which item and labels slide onto the wrong headlines
SAVE_EVERY = 100


def label_headlines(n: int = 3000):
    """Have the llm label a random sample of stored headlines and append them to LABELS_FILE."""
    from app.models import Session, Headline, Article, Agency

    if llm.backend() is None:
        return
    with Session() as s:
        rows = s.query(Headline.title, Agency.name).join(Headline.article).join(Article.agency).all()
    done = set(pd.read_csv(LABELS_FILE)['title']) if os.path.exists(LABELS_FILE) else set()
    pool = list({title: agency for title, agency in rows if title not in done}.items())
    sample = random.sample(pool, min(n, len(pool)))

    t = time.time()
    labeled = []
    for i, (title, agency) in enumerate(sample, start=1):
        result = llm.complete_json(LABEL_PROMPT.format(agency=agency, title=title.strip()), SCHEMA, max_tokens=16)
        if result:
            labeled.append({'title': title, 'agency': agency, 'label': result['label']})
        if i % SAVE_EVERY == 0 or i == len(sample):
            # Append as we go so an interrupted run keeps what it has done
            pd.DataFrame(labeled).to_csv(LABELS_FILE, mode='a', header=not os.path.exists(LABELS_FILE),
                                         index=False)
            labeled = []
            logger.info("Labeled %d of %d headlines in %.0fs", i, len(sample), time.time() - t)
    if os.path.exists(LABELS_FILE):
        logger.info("Label counts so far: %s", pd.read_csv(LABELS_FILE)['label'].value_counts().to_dict())


def train():
    """Fit the fallback classifier on LABELS_FILE and save it with a conservative cutoff.

    Static embeddings separate news from news-shaped lifestyle content poorly, so the cutoff is chosen for
    precision: only drop a headline when the classifier is confident it isn't news. Wrongly dropping news damages
    every analysis; letting a recipe through costs little."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import cross_val_predict

    df = pd.read_csv(LABELS_FILE).drop_duplicates('title', keep='last')
    X = embed(df['title'].tolist())
    y = (df['label'] == 'news').astype(int).to_numpy()
    model = LogisticRegression(max_iter=2000)
    held_out = cross_val_predict(model, X, y, cv=5, method='predict_proba')[:, 1]

    best = None
    for threshold in np.arange(0.05, 0.55, 0.05):
        dropped = held_out < threshold
        if not dropped.any():
            continue
        precision = (y[dropped] == 0).mean()
        caught = dropped[y == 0].mean()
        if precision >= FALLBACK_PRECISION and (best is None or caught > best['caught']):
            best = {'threshold': float(threshold), 'precision': float(precision), 'caught': float(caught),
                    'news_lost': float(dropped[y == 1].mean())}
    if best is None:
        logger.warning("No cutoff reaches %.0f%% precision; the fallback classifier won't drop anything",
                       100 * FALLBACK_PRECISION)
        best = {'threshold': 0.0, 'precision': float('nan'), 'caught': 0.0, 'news_lost': 0.0}

    model.fit(X, y)
    joblib.dump({'model': model, 'embedding_model': EMBEDDING_MODEL, 'trained_on': len(df), **best}, MODEL_FILE)
    logger.info("Trained fallback news filter on %d headlines: cutoff %.2f drops non-news with %.0f%% precision, "
                "catching %.0f%% of it and losing %.1f%% of real news", len(df), best['threshold'],
                100 * best['precision'], 100 * best['caught'], 100 * best['news_lost'])


_model = None


def _load() -> Optional[dict]:
    global _model
    if _model is None and os.path.exists(MODEL_FILE):
        _model = joblib.load(MODEL_FILE)
        if _model['embedding_model'] != EMBEDDING_MODEL or 'threshold' not in _model:
            logger.warning("News filter model is out of date; retrain it with --train-newsfilter")
            _model = None
    return _model


def score(titles: list[str], agency: str) -> list[Optional[float]]:
    """1.0 for news, 0.0 for non-news or junk, None if it can't be judged (treated as news).

    The llm labels each headline when one is available: it's local, free and much more accurate. Otherwise the
    fallback classifier only marks headlines it's confident aren't news."""
    if not len(titles):
        return []
    if llm.backend() is not None:
        scores = []
        for title in titles:
            result = llm.complete_json(LABEL_PROMPT.format(agency=agency, title=title.strip()), SCHEMA,
                                       max_tokens=16)
            scores.append(None if result is None else float(result['label'] == 'news'))
        return scores
    model = _load()
    if model is None:
        return [None] * len(titles)
    probabilities = model['model'].predict_proba(embed(titles))[:, 1]
    return [float(p >= model['threshold']) for p in probabilities]


def rescore_all():
    """Score every stored headline, e.g. after retraining. With an llm this takes a while (~0.1s a headline)."""
    from app.models import Session, Headline, Article, Agency
    with Session() as s:
        rows = s.query(Headline.id, Headline.title, Agency.name).join(Headline.article).join(Article.agency).all()
    df = pd.DataFrame(rows, columns=['id', 'title', 'agency'])
    t = time.time()
    for n, (agency, group) in enumerate(df.groupby('agency'), start=1):
        scores = score(group['title'].tolist(), agency)
        with Session() as s:
            s.execute(update(Headline), [{'id': int(i), 'news_score': v} for i, v in zip(group['id'], scores)])
            s.commit()
        logger.info("Rescored %s (%d of %d agencies, %.0fs)", agency, n, df['agency'].nunique(), time.time() - t)
    with Session() as s:
        total = s.query(Headline).count()
        news = s.query(Headline).filter(Headline.news_score >= NEWS_THRESHOLD).count()
    logger.info("Rescored %d headlines, %.1f%% news", total, 100 * news / max(total, 1))
