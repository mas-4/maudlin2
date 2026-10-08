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
from app.analysis import motif_signals as ms
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

MODEL = os.path.join(Config.data, 'filing_confidence.json')
CURATION_LOG = os.path.join(Config.data, 'validation', 'curation_log.jsonl')
SOURCES = ['narrative', 'Focus Group']  # anything else is a fact-checker; what's retold on the shows counts as what's
# retold online (4 decisions on its own on Oct 8: a weight of its own learned 'always kept' from them)
SAME_AS = {'shows': 'narrative'}
FEATURES = mr.FACTS + ['score', 'rank', 'margin', 'motifs of the claim'] + \
    [f'from {s}' for s in SOURCES] + ms.CHEAP + ['rerank', 'judge']  # the many signals (motif_signals.py), Oct 8
# Never 'sure', whatever the fit: a filing in a motif the model made for this claim alone (alike by birth: whether
# that motif should be is another question), and claims from a source with too few of the person's decisions to
# have been tested (Oct 8: the shows, 4)
MIN_TESTED = 30
RETRAIN = td(days=1)
MIN_EACH = 40  # kept and removed filings needed to train
# Where a weakly filed claim might belong instead (Oct 8, the person: help them correct weak fits rather than look
# for better motifs by hand): for each claim with a filing under WEAK in their motifs (unchecked, or confirmed and up
# for a second look), the CANDIDATES motifs of theirs the shortlist ranks highest that it isn't in, each given a fit by
# this model, the best BETTER_SHOWN kept from BETTER_MIN up
ALTERNATIVES = os.path.join(Config.data, 'motifs', 'filing_alternatives.json')  # claim key -> {'model', 'motifs'}
WEAK = 0.5
CANDIDATES = 12
BETTER_SHOWN = 3
BETTER_MIN = 0.3
SURE = 0.95  # precision the 'sure' threshold has to reach, held out


def decisions(path: str = CURATION_LOG, hand: bool = False) -> dict[tuple[str, str], bool]:
    """(claim key, motif id) -> kept, the person's last word on each filing in the curation log. With `hand`, also
    the filings they made themselves (a claim added to another motif, filed by hand, or the motif it was moved to):
    the model's misses (286 'also' by Oct 8)"""
    out = {}

    def one(a: dict):
        act = a.get('action')
        if act == 'check' and a.get('answer') in ('yes', 'no'):
            out[(mi.key(a['claim']), a['id'])] = a['answer'] == 'yes'
        elif act in ('unfile', 'reject', 'not this motif') and a.get('claim') and a.get('id'):
            out[(mi.key(a['claim']), a['id'])] = False
        elif act == 'move' and a.get('claim') and a.get('source'):
            out[(mi.key(a['claim']), a['source'])] = False
            if hand and a.get('target'):
                out[(mi.key(a['claim']), a['target'])] = True
        elif hand and act == 'also' and a.get('claim') and a.get('target'):
            out[(mi.key(a['claim']), a['target'])] = True
        elif hand and act == 'file' and a.get('claim') and a.get('id'):
            out[(mi.key(a['claim']), a['id'])] = True
        elif act == 'batch':
            for step in a.get('steps') or []:
                if isinstance(step, dict):
                    one(step)
    for r in log_rows(path):
        if isinstance(r.get('action'), dict) and r.get('by') != 'claude':
            one(r['action'])
    return out


def log_rows(path: str = CURATION_LOG) -> list[dict]:
    """The curation log, oldest first: from the curation database (without changes taken back by going back to a
    checkpoint) when it's the log asked for and the database has it, else from the file"""
    if path == CURATION_LOG:
        from app.analysis import curation_db
        try:
            rows = curation_db.actions()
            if rows:
                return rows
        except Exception as e:  # noqa: BLE001 - the file has it all too
            logger.warning("Curation database unreadable (%s); reading the log file", e)
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


class Scorer:
    """Features of (claim, motif) pairs against one index, the shortlist's work done once per claim; the costly
    signals (the reranker, the filing model's yes or no) asked only of the pairs scored, and kept"""

    def __init__(self, index: dict, w: dict, vec: mr.Vectors | None = None):
        self.index, self.w, self.vec = index, w, vec or mr.Vectors()
        self.signals = ms.Signals(index, self.vec)
        self.entries = [e for e in mi.live(index) if e['claims']]
        self.at = {e['id']: n for n, e in enumerate(self.entries)}
        self.weights = np.array([w['weights'][f] for f in mr.FACTS])
        self.motifs_of = defaultdict(set)
        for e in self.entries:
            for c in e['claims']:
                self.motifs_of[mi.key(c['claim'])].add(e['id'])

    def candidates(self, claim: str, n: int = CANDIDATES) -> list[str]:
        """The person's motifs (yours) the shortlist ranks highest for a claim, but those it's in or a person said it
        isn't"""
        k = mi.key(claim)
        F = mr.facts(self.entries, claim, self.vec, leave_out=True)
        score = F @ self.weights + self.w['bias']
        return [self.entries[i]['id'] for i in np.argsort(-score)
                if yours(self.entries[i]) and self.entries[i]['id'] not in self.motifs_of.get(k, ())
                and k not in self.entries[i].get('not_claims', [])][:n]

    def rows(self, claim: str, ids: list[str], source: str = '') -> np.ndarray:
        """A row of FEATURES for each motif in `ids` against the claim (all of them in this index's live motifs)"""
        F = mr.facts(self.entries, claim, self.vec, leave_out=True)
        score = F @ self.weights + self.w['bias']
        order = np.argsort(-score)
        rank = np.empty(len(order))
        rank[order] = np.arange(len(order))
        cheap = self.signals.cheap(claim, leave_out=True)
        at = [self.signals.at[eid] for eid in ids]
        rerank = logit(self.signals.rerank(claim, at, leave_out=True))
        judge = logit(self.signals.judge(claim, at, leave_out=True))
        out = []
        for i, eid in enumerate(ids):
            n = self.at[eid]
            others = np.delete(score, n)
            out.append(list(F[n]) + [score[n], np.log1p(rank[n]), score[n] - (others.max() if len(others) else 0.0),
                                     len(self.motifs_of.get(mi.key(claim), ()))]
                       + [float(SAME_AS.get(source, source) == s) for s in SOURCES]
                       + [float(cheap[c][at[i]]) for c in ms.CHEAP] + [rerank[i], judge[i]])
        return np.array(out)


def labeled(index: dict, hand: bool = False) -> list[tuple[str, str, str, bool]]:
    """(claim, motif id, source, kept) for each filing the person decided on (with `hand`, made themselves too), its
    motif still live, its claim's text known (filed now, or in the log's own words)"""
    text, source = {}, {}
    for e in mi.live(index):
        for c in e['claims']:
            text[mi.key(c['claim'])] = c['claim']
            source[mi.key(c['claim'])] = c.get('source', '')
    # A removed claim may be in no motif now: its words from the log
    for r in log_rows():
        a = r.get('action')
        for step in ([a] + (a.get('steps') or [])) if isinstance(a, dict) else []:
            if isinstance(step, dict) and isinstance(step.get('claim'), str):
                text.setdefault(mi.key(step['claim']), step['claim'])
    live = {e['id'] for e in mi.live(index) if e['claims'] and yours(e)}
    return [(text[k], eid, source.get(k, ''), kept) for (k, eid), kept in decisions(hand=hand).items()
            if eid in live and k in text]


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
    scorer.signals.prepare([c for c, _ in by_claim])
    X, y, groups = [], [], []
    for (claim, source), items in by_claim.items():
        X.extend(scorer.rows(claim, [eid for eid, _ in items], source))
        y.extend(ok for _, ok in items)
        groups.extend([mi.key(claim)] * len(items))
    scorer.signals.save()
    X, y = np.array(X), np.array(y, dtype=bool)
    # A taught reranker learned these very decisions: its scores on them would look better than they are, so the model
    # learns from scores by rerankers that never saw each claim (reranker_teach.held_out)
    from app.analysis import reranker_teach
    tag = scorer.signals.rerank_tag
    if tag != 'base':
        held, col = reranker_teach.held_out(), FEATURES.index('rerank')
        keys = [f'{mi.key(c)}|{e}' for (c, _), items in by_claim.items() for e, _ in items]
        for i, k in enumerate(keys):
            if k in held:
                X[i, col] = logit(np.array([held[k]]))[0]
    test = evaluate(X, y, groups)
    test.pop('p')
    model, mu, sd = _fit(X, y)
    coef = model.coef_[0] / sd
    out = {'weights': dict(zip(FEATURES, coef.round(5).tolist())), 'bias': round(float(model.intercept_[0] - mu @ coef), 5),
           'test': test, 'retriever_at': w['at'], 'reranker': tag, 'at': dt.now().isoformat(timespec='seconds')}
    write_json(MODEL, out, indent=1)
    logger.info("Filing confidence trained on %d filings (%d kept): AUC %.3f held out, sure from %s", test['filings'],
                test['kept'], test['auc'], test['sure_at'])
    return out


def model(retrain: bool = False) -> dict | None:
    """The current model; retrained when a day old (or missing) only if `retrain` (the hourly run: training asks the
    filing model about new decisions, so never from the checker)"""
    m = read_json(MODEL, None)
    if m and set(m['weights']) != set(FEATURES):
        m = None  # trained on other signals
    if retrain and m:
        from app.analysis import reranker_teach
        if m.get('reranker', 'base') != reranker_teach.tag():
            m = None  # a newly taught reranker: learn how far to trust it
    if retrain and (not m or dt.now() - dt.fromisoformat(m['at']) > RETRAIN):
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


def score(index: dict | None = None, m: dict | None = None, skip: set | None = None,
          budget: float | None = None, confirmed: bool = False) -> dict[tuple[str, str], float]:
    """(claim key, motif id) -> the chance a person keeps it, for every filing in the person's motifs nobody has
    checked (with `confirmed`, those they confirmed instead: the second look), but those in `skip` (already scored),
    for at most `budget` seconds"""
    import time
    index = index if index is not None else mi.load()
    m = m or model()
    w = mr.weights()
    if not m or not w:
        return {}
    started = time.time()
    scorer = Scorer(index, w)
    coef = np.array([m['weights'][f] for f in FEATURES])
    todo = defaultdict(list)
    for e in scorer.entries:
        if not yours(e):
            continue
        for c in e['claims']:
            wanted = c.get('checked') == 'yes' and not c.get('rechecked') if confirmed else not c.get('checked')
            if wanted and (mi.key(c['claim']), e['id']) not in (skip or ()):
                todo[(c['claim'], c.get('source', ''))].append(e['id'])
    scorer.signals.prepare([c for c, _ in todo])
    out = {}
    for (claim, source), ids in todo.items():
        if budget is not None and time.time() - started > budget:
            break
        z = scorer.rows(claim, ids, source) @ coef + m['bias']
        for eid, v in zip(ids, z):
            out[(mi.key(claim), eid)] = round(float(1 / (1 + np.exp(-v))), 3)
    scorer.signals.save()
    return out


def weak_claims(index: dict, m: dict) -> dict[str, tuple[str, str]]:
    """Claim key -> (claim, source) for each claim with a filing in the person's motifs this model gives under WEAK:
    unchecked, or confirmed but not looked at again (and not filed by the person's own hand)"""
    hand = {k for k, ok in decisions(hand=True).items() if ok} - {k for k, ok in decisions().items() if ok}
    out = {}
    for e in mi.live(index):
        if not yours(e):
            continue
        for c in e['claims']:
            k = mi.key(c['claim'])
            if c.get('fit_model') != m['at'] or c.get('fit') is None or c['fit'] >= WEAK:
                continue
            if not c.get('checked') or (c.get('checked') == 'yes' and not c.get('rechecked') and (k, e['id']) not in hand):
                out.setdefault(k, (c['claim'], c.get('source', '')))
    return out


def alternatives(index: dict, m: dict, budget: float | None = None) -> int:
    """Where each weakly filed claim might belong instead (see WEAK), kept in ALTERNATIVES for the checker; claims
    already done by this model skipped, for at most `budget` seconds; how many claims were worked out"""
    import time
    started = time.time()
    store = read_json(ALTERNATIVES, {})
    weak = weak_claims(index, m)
    store = {k: v for k, v in store.items() if k in weak}  # no longer weak: gone
    todo = {k: v for k, v in weak.items() if store.get(k, {}).get('model') != m['at']}
    if not todo:
        write_json(ALTERNATIVES, store)
        return 0
    w = mr.weights()
    scorer = Scorer(index, w)
    coef = np.array([m['weights'][f] for f in FEATURES])
    scorer.signals.prepare([c for c, _ in todo.values()])
    done = 0
    for k, (claim, source) in todo.items():
        if budget is not None and time.time() - started > budget:
            break
        ids = scorer.candidates(claim)
        if not ids:
            continue
        p = 1 / (1 + np.exp(-(scorer.rows(claim, ids, source) @ coef + m['bias'])))
        best = sorted(((eid, round(float(v), 3)) for eid, v in zip(ids, p) if v >= BETTER_MIN), key=lambda x: -x[1])
        store[k] = {'model': m['at'], 'motifs': [list(x) for x in best[:BETTER_SHOWN]]}
        done += 1
    scorer.signals.save()
    write_json(ALTERNATIVES, store)
    logger.info("Filing confidence: alternatives for %d weakly filed claims (%d left)", done, len(todo) - done)
    return done


def better(index: dict, claim: str) -> list[dict]:
    """The motifs a weakly filed claim might belong in instead ({id, name, fit}), those it's in now left out"""
    k = mi.key(claim)
    x = read_json(ALTERNATIVES, {}).get(k)
    if not x:
        return []
    entries = index['entries']
    return [{'id': eid, 'name': entries[eid]['name'], 'fit': fit} for eid, fit in x['motifs']
            if eid in entries and not entries[eid].get('merged_into')
            and k not in {mi.key(c['claim']) for c in entries[eid]['claims']}
            and k not in entries[eid].get('not_claims', [])]  # a person said it isn't this one (✕): gone at once


def refresh(budget: float | None = None) -> int:
    """The hourly run's part: retrain if a day old, then work out the fit of every unchecked filing in the person's
    motifs that has none from this model yet, and keep it on the filing (motif_index.set_fits), for the checker to
    read"""
    m = model(retrain=True)
    if not m:
        return 0
    index = mi.load()
    have = {(mi.key(c['claim']), e['id']) for e in mi.live(index) for c in e['claims']
            if c.get('fit_model') == m['at'] and c.get('fit') is not None}
    import time
    started = time.time()
    fits = score(index, m, skip=have, budget=budget)
    # then the person's confirmed filings, for the second look (most of their signals are cached from training)
    left = None if budget is None else max(0.0, budget - (time.time() - started))
    seconds = score(index, m, skip=have, budget=left, confirmed=True) if left is None or left > 10 else {}
    if fits or seconds:
        mi.set_fits({**fits, **seconds}, m['at'])
    left = None if budget is None else max(0.0, budget - (time.time() - started))
    if left is None or left > 20:
        try:
            alternatives(mi.load(), m, left)
        except Exception as e:  # noqa: BLE001 - suggestions are extra; the next run tries again
            logger.warning("Filing confidence: alternatives failed (%s)", e)
    logger.info("Filing confidence: %d new filings and %d confirmed scored (model of %s, AUC %.3f held out)", len(fits),
                len(seconds), m['at'], m['test']['auc'])
    return len(fits) + len(seconds)
