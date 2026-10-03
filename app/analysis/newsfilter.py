"""Judges each headline with the local llm, one headline per request (small models lose track of numbered
batches), in a single call that returns three things:

- kind: news, or not (lifestyle, shopping, page furniture). Non-news stays out of the analyses.
- event: how good or bad the reported event is for the people it affects, -2 to 2, whoever reports it.
- loaded: how loaded the outlet's own wording is, 0 (plain) to 2 (built to provoke).
- emotions: up to three feelings it's most likely to stir, strongest first (fear, anger, sadness, disgust, surprise,
  joy, hope or neutral), scored ranked-choice style when averaged.

Event and wording are scored apart because word-list sentiment (VADER, AFINN) mostly measures the event: every
headline about a deadly crash reads negative whoever writes it. The rubric asks the model to name who is
affected and how before scoring, which fixed most errors on hard cases (strikes and attacks read from the
attacker's side).

When no llm is running, `--label-headlines` + `--train-newsfilter` provide a fallback news classifier. It's much
weaker than the llm, so it uses a cutoff chosen to almost never drop real news, and it gives no event or loaded
scores (the site falls back to VADER and AFINN for those)."""
import hashlib
import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime as dt
from typing import Optional

import joblib
import numpy as np
import pandas as pd
import pytz
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

PROMPT = """You are scoring a headline from {agency}'s front page. Judge only the headline's words.

kind:
- news: politics, government, world affairs, business and the economy, courts, crime, science, health, sports \
results and sports news, entertainment-industry news (releases, deals, awards), and any opinion, analysis or \
commentary on these, however sharply worded ("Trump's 'human printer' and the twisted magic of the MAGA \
cocoon", "Why house prices may be in trouble", "Miranda Lambert returns with new album")
- non_news: celebrity gossip and personal lives (romances, outfits, parties, photos), lifestyle (recipes, \
shopping and deals, product reviews, travel features, horoscopes, quizzes), evergreen how-to and advice, \
photo galleries ("Sydney Sweeney spills out of lacy bra", "2 habits that weaken your critical thinking", \
"Gallery: the week in pictures")
- junk: not a headline at all: navigation, section names, bylines, promos, newsletter signups, template text \
("Election '04", "More news", "Read the full story")

affected: first, in under 12 words, who the event affects and whether it helps or harms them.

event: how good or bad the reported event is for the people it affects, whoever reports it and whoever caused \
it. Attacks, strikes, arrests, deaths, losses and dangers are bad for the people on the receiving end.
-2: deaths, disasters, attacks, violence, serious harm ("Strike kills 12", "Heat deaths top 34,000")
-1: setbacks, losses, conflict, threats, risk, worry ("Factory lays off 1,400", "Bridge damaged in strike")
0: neutral, procedural or mixed ("Senate schedules vote", "Polls show tight race")
+1: progress, relief, gains, wins ("Inflation eases", "Team wins series")
+2: lives saved, major breakthroughs, celebrations ("Hostages freed", "Cure approved")

loaded: how much the outlet's own word choice adds emotion, judgment or alarm beyond the facts. Words quoted \
from a source do not count. Most headlines are 0.
0: plain wording ("Senator criticizes bill", "Man arrested after shooting", "Investigators say attack was planned")
1: one or two charged words the outlet chose ("slams", "blasts", "chaos", "meltdown", "regime", "furious")
2: built to provoke: insults, sensational or partisan framing, ALL CAPS, outrage bait ("MELTDOWN: Dems lose \
their minds", "Clueless senator humiliated")

emotions: the feelings the headline is most likely to stir in a reader, from the event and the wording together:
one to three of these, strongest first. List only feelings it really carries; plain information is just neutral.
- fear: a threat, danger or risk to people: attacks, terror plots, war escalation, disease, disasters ahead
- anger: outrage at someone's conduct: blame, injustice, hypocrisy, abuse of power, a person or group attacked
- sadness: loss already suffered: deaths, tragedies, grief, decline, failure
- disgust: revulsion: depravity, corruption, sordid scandal
- surprise: something unexpected or astonishing
- joy: celebration, victory, delight
- hope: progress, relief, a solution, a way forward
- neutral: plain information that evokes no particular feeling

Headline: {title}"""

EMOTIONS = ["fear", "anger", "sadness", "disgust", "surprise", "joy", "hope", "neutral"]
EMOTION_EMOJI = {'fear': '😨', 'anger': '😠', 'sadness': '😢', 'disgust': '🤢', 'surprise': '😲', 'joy': '😄',
                 'hope': '🤞', 'neutral': '🥛'}  # neutral is a glass of milk

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": ["news", "non_news", "junk"]},
        "affected": {"type": "string", "maxLength": 100},  # written before the scores, it steers them
        "event": {"type": "integer", "enum": [-2, -1, 0, 1, 2]},
        "loaded": {"type": "integer", "enum": [0, 1, 2]},
        "emotions": {"type": "array", "items": {"type": "string", "enum": EMOTIONS}, "minItems": 1, "maxItems": 3},
    },
    "required": ["kind", "affected", "event", "loaded", "emotions"],
    "additionalProperties": False,
}
MAX_TOKENS = 96
# Changes whenever the prompt or schema does, so every score can be traced to the exact rubric that made it
RUBRIC_ID = hashlib.sha1((PROMPT + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:8]
FALLBACK_JUDGE = 'fallback classifier'
EMPTY = {'news_score': None, 'event_score': None, 'loaded_score': None, 'emotion': None, 'emotion_ranks': None,
         'scored_by': None, 'scored_at': None, 'affected': None}
PARALLEL_REQUESTS = 4


def ranked(emotions: list[str]) -> dict:
    """The model's ranked emotions, deduplicated: the top one, and all of them in order for soft scoring."""
    order = list(dict.fromkeys(e for e in emotions if e in EMOTIONS))[:3] or ['neutral']
    return {'emotion': order[0], 'emotion_ranks': ','.join(order)}


def emotion_weights(ranks: Optional[str]) -> dict[str, float]:
    """Ranked choice, Borda style: a headline's one vote split 3:2:1 across its ranked emotions (normalized, so a
    headline with one emotion gives it the whole vote). Averaging these across a story or an outlet lets feelings
    that are often second choice show up, instead of only counting top picks."""
    if not isinstance(ranks, str) or not ranks:
        return {}
    order = ranks.split(',')
    points = {e: len(order) - i for i, e in enumerate(order)}
    total = sum(points.values())
    return {e: p / total for e, p in points.items()}


def judge(title: str, agency: str) -> Optional[dict]:
    return llm.complete_json(PROMPT.format(agency=agency, title=title.strip()), SCHEMA, max_tokens=MAX_TOKENS)


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
        result = judge(title, agency)
        if result:
            labeled.append({'title': title, 'agency': agency, 'label': result['kind']})
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


def judge_id() -> str:
    """Who is scoring right now: the llm and the rubric version, e.g. "qwen3:8b rubric:1a2b3c4d"."""
    llm.backend()  # resolves which model is in use
    return f'{llm.model()} rubric:{RUBRIC_ID}'


def assess(titles: list[str], agency: str) -> list[dict]:
    """For each title: news_score (1.0 news, 0.0 not, None if it couldn't be judged, which counts as news),
    event_score and loaded_score (None without an llm), and the provenance of those scores (scored_by, scored_at,
    and the model's 'affected' note)."""
    if not len(titles):
        return []
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    if llm.backend() is not None:
        # Several requests at once let the server batch them on the gpu (needs OLLAMA_NUM_PARALLEL > 1)
        with ThreadPoolExecutor(PARALLEL_REQUESTS) as pool:
            judged = list(pool.map(lambda title: judge(title, agency), titles))
        by = judge_id()
        return [dict(EMPTY) if r is None else
                {'news_score': float(r['kind'] == 'news'), 'event_score': float(r['event']),
                 'loaded_score': float(r['loaded']), **ranked(r['emotions']), 'scored_by': by, 'scored_at': now,
                 'affected': (r.get('affected') or '')[:128] or None} for r in judged]
    model = _load()
    if model is None:
        return [dict(EMPTY) for _ in titles]
    probabilities = model['model'].predict_proba(embed(titles))[:, 1]
    return [{**EMPTY, 'news_score': float(p >= model['threshold']), 'scored_by': FALLBACK_JUDGE, 'scored_at': now}
            for p in probabilities]


def rescore_all(only_missing: bool = False):
    """Judge stored headlines again, e.g. after changing the rubric, then recompute the stories' framing from the
    new scores. `only_missing` fills in just the headlines that have no scores yet (a failed or interrupted run)."""
    from app.models import Session, Headline, Article, Agency
    with Session() as s:
        query = s.query(Headline.id, Headline.title, Agency.name).join(Headline.article).join(Article.agency)
        if only_missing:
            query = query.filter(Headline.event_score.is_(None) | Headline.emotion_ranks.is_(None))
        rows = query.all()
    df = pd.DataFrame(rows, columns=['id', 'title', 'agency'])
    t = time.time()
    for n, (agency, group) in enumerate(df.groupby('agency'), start=1):
        results = assess(group['title'].tolist(), agency)
        with Session() as s:
            s.execute(update(Headline), [{'id': int(i), **r} for i, r in zip(group['id'], results)])
            s.commit()
        logger.info("Rescored %s (%d of %d agencies, %.0fs)", agency, n, df['agency'].nunique(), time.time() - t)
    with Session() as s:
        total = s.query(Headline).count()
        news = s.query(Headline).filter(Headline.news_score >= NEWS_THRESHOLD).count()
    logger.info("Rescored %d headlines, %.1f%% news", total, 100 * news / max(total, 1))
    from app.analysis.stories import refresh_story_sentiment
    refresh_story_sentiment()
