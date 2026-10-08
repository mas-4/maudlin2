"""How sure we are that a claim the model filed under a motif belongs there (Oct 8): so the person checks the doubtful
filings and can pass the sure ones in one go, instead of every filing one by one in the order of its motif's size.

Trained on the person's own decisions in the curation log: a filing they ticked ✓ fits is kept; one they took out
(✕, unfile, moved to another motif, 'not this motif') is removed. Each (claim, motif) pair is described by the
filing shortlist's likeness measures (motif_retriever.FACTS, the claim held out of its motif), the shortlist's score
for the motif and how it ranks among all motifs for this claim, how many motifs the claim is in, where the claim
came from. A logistic regression weighs them (train(), daily, seconds); score() gives each unchecked filing a chance
it would be kept. Only filings in the person's own motifs (those they've marked done) are scored or learned from: a
motif the model made and nobody has shaped is no measure of anything (Oct 8: a claim scored 100% in the motif the
model had just named from it)."""
import json
import os
from collections import defaultdict
from datetime import datetime as dt
from datetime import timedelta as td

import numpy as np

from app.analysis import motif_index as mi
from app.analysis import motif_retriever as mr
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

MODEL = os.path.join(Config.data, 'filing_confidence.json')
CURATION_LOG = os.path.join(Config.data, 'validation', 'curation_log.jsonl')
SOURCES = ['narrative', 'Focus Group']  # anything else is a fact-checker; what's retold on the shows counts as what's
# retold online (4 decisions on its own on Oct 8: a weight of its own learned 'always kept' from them)
SAME_AS = {'shows': 'narrative'}
FEATURES = mr.FACTS + ['score', 'rank', 'margin', 'motifs of the claim'] + \
    [f'from {s}' for s in SOURCES]
# Never 'sure', whatever the fit: a filing in a motif the model made for this claim alone (alike by birth: whether
# that motif should be is another question), and claims from a source with too few of the person's decisions to
# have been tested (Oct 8: the shows, 4)
MIN_TESTED = 30
RETRAIN = td(days=1)
MIN_EACH = 40  # kept and removed filings needed to train
SURE = 0.95  # precision the 'sure' threshold has to reach, held out


def decisions(path: str = CURATION_LOG) -> dict[tuple[str, str], bool]:
    """(claim key, motif id) -> kept, the person's last word on each filing in the curation log"""
    out = {}

    def one(a: dict):
        act = a.get('action')
        if act == 'check' and a.get('answer') in ('yes', 'no'):
            out[(mi.key(a['claim']), a['id'])] = a['answer'] == 'yes'
        elif act in ('unfile', 'reject', 'not this motif') and a.get('claim') and a.get('id'):
            out[(mi.key(a['claim']), a['id'])] = False
        elif act == 'move' and a.get('claim') and a.get('source'):
            out[(mi.key(a['claim']), a['source'])] = False
        elif act == 'batch':
            for step in a.get('steps') or []:
                if isinstance(step, dict):
                    one(step)
    try:
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r.get('action'), dict) and r.get('by') != 'claude':
                    one(r['action'])
    except OSError:
        pass
    return out


class Scorer:
    """Features of (claim, motif) pairs against one index, the shortlist's work done once per claim"""

    def __init__(self, index: dict, w: dict, vec: mr.Vectors | None = None):
        self.index, self.w, self.vec = index, w, vec or mr.Vectors()
        self.entries = [e for e in mi.live(index) if e['claims']]
        self.at = {e['id']: n for n, e in enumerate(self.entries)}
        self.weights = np.array([w['weights'][f] for f in mr.FACTS])
        self.motifs_of = defaultdict(set)
        for e in self.entries:
            for c in e['claims']:
                self.motifs_of[mi.key(c['claim'])].add(e['id'])

    def rows(self, claim: str, ids: list[str], source: str = '') -> np.ndarray:
        """A row of FEATURES for each motif in `ids` against the claim (all of them in this index's live motifs)"""
        F = mr.facts(self.entries, claim, self.vec, leave_out=True)
        score = F @ self.weights + self.w['bias']
        order = np.argsort(-score)
        rank = np.empty(len(order))
        rank[order] = np.arange(len(order))
        out = []
        for eid in ids:
            n = self.at[eid]
            others = np.delete(score, n)
            out.append(list(F[n]) + [score[n], np.log1p(rank[n]), score[n] - (others.max() if len(others) else 0.0),
                                     len(self.motifs_of.get(mi.key(claim), ()))]
                       + [float(SAME_AS.get(source, source) == s) for s in SOURCES])
        return np.array(out)


def labeled(index: dict) -> list[tuple[str, str, str, bool]]:
    """(claim, motif id, source, kept) for each filing the person decided on, its motif still live, its claim's text
    known (filed now, or in the log's own words)"""
    text, source = {}, {}
    for e in mi.live(index):
        for c in e['claims']:
            text[mi.key(c['claim'])] = c['claim']
            source[mi.key(c['claim'])] = c.get('source', '')
    # A removed claim may be in no motif now: its words from the log
    try:
        with open(CURATION_LOG) as f:
            for line in f:
                a = (json.loads(line) or {}).get('action')
                for step in ([a] + (a.get('steps') or [])) if isinstance(a, dict) else []:
                    if isinstance(step, dict) and isinstance(step.get('claim'), str):
                        text.setdefault(mi.key(step['claim']), step['claim'])
    except (OSError, ValueError):
        pass
    live = {e['id'] for e in mi.live(index) if e['claims'] and yours(e)}
    return [(text[k], eid, source.get(k, ''), kept) for (k, eid), kept in decisions().items() if eid in live and k in text]


def _fit(X: np.ndarray, y: np.ndarray):
    from sklearn.linear_model import LogisticRegression
    mu, sd = X.mean(0), X.std(0) + 1e-9
    model = LogisticRegression(max_iter=2000, C=0.5).fit((X - mu) / sd, y)
    return model, mu, sd


def evaluate(X: np.ndarray, y: np.ndarray, groups: list[str], folds: int = 5) -> dict:
    """Each filing scored by a model that never saw its claim (grouped folds): AUC, and for each threshold how many of
    the kept filings it would pass and how many of those it passes would have been removed"""
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import GroupKFold
    p = np.zeros(len(y))
    for tr, te in GroupKFold(folds).split(X, y, groups):
        model, mu, sd = _fit(X[tr], y[tr])
        p[te] = model.predict_proba((X[te] - mu) / sd)[:, 1]
    out = {'auc': round(float(roc_auc_score(y, p)), 3), 'filings': int(len(y)), 'kept': int(y.sum()), 'thresholds': []}
    for t in (0.5, 0.7, 0.8, 0.85, 0.9, 0.95, 0.97):
        passed = p >= t
        out['thresholds'].append({'at': t, 'passes': int(passed.sum()), 'of kept': round(float(passed[y].mean()), 3),
                                  'precision': round(float(y[passed].mean()), 3) if passed.any() else None})
    sure = [r for r in out['thresholds'] if r['precision'] is not None and r['precision'] >= SURE and r['passes'] >= 20]
    out['sure_at'] = sure[0]['at'] if sure else None
    out['p'] = p
    return out


def train(index: dict | None = None) -> dict | None:
    """The model, from the person's decisions; None with too few of either kind, or no shortlist weights. Saved to
    MODEL with its held-out test"""
    index = index if index is not None else mi.load()
    w = mr.weights()
    pairs = labeled(index)
    kept = sum(p[3] for p in pairs)
    if not w or kept < MIN_EACH or len(pairs) - kept < MIN_EACH:
        return None
    scorer = Scorer(index, w)
    by_claim = defaultdict(list)
    for claim, eid, source, ok in pairs:
        by_claim[(claim, source)].append((eid, ok))
    X, y, groups = [], [], []
    for (claim, source), items in by_claim.items():
        X.extend(scorer.rows(claim, [eid for eid, _ in items], source))
        y.extend(ok for _, ok in items)
        groups.extend([mi.key(claim)] * len(items))
    X, y = np.array(X), np.array(y, dtype=bool)
    test = evaluate(X, y, groups)
    test.pop('p')
    model, mu, sd = _fit(X, y)
    coef = model.coef_[0] / sd
    out = {'weights': dict(zip(FEATURES, coef.round(5).tolist())), 'bias': round(float(model.intercept_[0] - mu @ coef), 5),
           'test': test, 'retriever_at': w['at'], 'at': dt.now().isoformat(timespec='seconds')}
    write_json(MODEL, out, indent=1)
    logger.info("Filing confidence trained on %d filings (%d kept): AUC %.3f held out, sure from %s", test['filings'],
                test['kept'], test['auc'], test['sure_at'])
    return out


def model() -> dict | None:
    """The current model, retrained when a day old (or missing)"""
    m = read_json(MODEL, None)
    if not m or dt.now() - dt.fromisoformat(m['at']) > RETRAIN:
        try:
            m = train() or m
        except Exception as e:  # noqa: BLE001 - the old model, or none: the check list keeps its old order
            logger.warning("Filing confidence: training failed (%s)", e)
    return m


def yours(entry: dict) -> bool:
    """A motif the person has shaped: marked done (every motif a person made is; the model's start out not done)"""
    return bool(entry.get('done'))


def tested_sources(index: dict) -> set[str]:
    """Sources (SOURCES, 'shows', or a fact-checker's name as 'checker') with MIN_TESTED decisions of the person's"""
    from collections import Counter
    n = Counter(kind(p[2]) for p in labeled(index))
    return {k for k, v in n.items() if v >= MIN_TESTED}


def kind(source: str) -> str:
    return source if source in SOURCES or source in SAME_AS else 'checker'


def can_be_sure(index: dict, claim: str, eid: str, source: str, tested: set[str]) -> bool:
    """Whether a filing may be passed as sure at all (see MIN_TESTED)"""
    k = mi.key(claim)
    e = index['entries'].get(eid) or {}
    others = {mi.key(c['claim']) for c in e.get('claims', [])} - {k}
    return bool(others) and kind(source) in tested


def score(index: dict | None = None, m: dict | None = None) -> dict[tuple[str, str], float]:
    """(claim key, motif id) -> the chance a person keeps it, for every filing nobody has checked"""
    index = index if index is not None else mi.load()
    m = m or model()
    w = mr.weights()
    if not m or not w:
        return {}
    scorer = Scorer(index, w)
    coef = np.array([m['weights'][f] for f in FEATURES])
    todo = defaultdict(list)
    for e in scorer.entries:
        if not yours(e):
            continue
        for c in e['claims']:
            if not c.get('checked'):
                todo[(c['claim'], c.get('source', ''))].append(e['id'])
    out = {}
    for (claim, source), ids in todo.items():
        z = scorer.rows(claim, ids, source) @ coef + m['bias']
        for eid, v in zip(ids, z):
            out[(mi.key(claim), eid)] = round(float(1 / (1 + np.exp(-v))), 3)
    return out
