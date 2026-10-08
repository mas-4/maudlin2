"""E4 a jury of readers and E6 asking what teaches most (docs/filing-experiments.md), on the person's decisions about
the model's filings (the confidence model's data).

First the pairs: each decision's features as the confidence model sees them (filing_confidence.Scorer, from the
caches), saved. E4: Gemma's yes or no on each pair as three readers (a folklorist, a rhetorician, a reader from the
claim's other side), P(yes) from the log-probabilities, cached (resumable); their mean and spread added to the model.
E6 (no model asked): simulate the person checking in different orders, from 50 decisions on, 25 at a time: at
random, the likeliest first (today's check list), or the least certain first; the held-out AUC after each step."""
import json
import math
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from sklearn.metrics import roc_auc_score  # noqa: E402

from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

PAIRS = os.path.join(harness.EXP, 'pairs.npz')
JURY = os.path.join(harness.EXP, 'jury.json')
READERS = {
    'folklorist': 'You are a folklorist who catalogs recurring story types in what people tell, the way Thompson '
                  'indexed motifs: you look past names and topics to the shape of the story.',
    'rhetorician': 'You are a rhetorician who studies how political claims persuade: the move each one makes, '
                   'whatever its topic.',
    'other side': "You are a reader from the political side opposite to the one telling this claim, reading it fairly "
                  "for what kind of story it is, not whether it's true.",
}


def build_pairs():
    index = mi.load()
    scorer = fc.Scorer(index, mr.weights())
    pairs = fc.labeled(index)
    by = defaultdict(list)
    for c, e, s, ok in pairs:
        by[(c, s)].append((e, ok))
    scorer.signals.prepare([c for c, _ in by])
    X, y, g, P = [], [], [], []
    for (c, s), items in by.items():
        X.extend(scorer.rows(c, [e for e, _ in items], s))
        y.extend(ok for _, ok in items)
        g.extend([mi.key(c)] * len(items))
        P.extend((c, e) for e, _ in items)
    scorer.signals.save()
    np.savez(PAIRS, X=np.array(X), y=np.array(y, bool), g=np.array(g), claims=np.array([p[0] for p in P]),
             motifs=np.array([p[1] for p in P]))


def ask_jury():
    import requests as rq
    from app.analysis.llm import OLLAMA_URL
    d = np.load(PAIRS)
    index = mi.load()
    sig = ms.Signals(index)
    try:
        with open(JURY) as f:
            done = json.load(f)
    except (OSError, ValueError):
        done = {}
    for i, (claim, eid) in enumerate(zip(d['claims'], d['motifs'])):
        e = index['entries'].get(str(eid))
        if e is None or str(eid) not in sig.at:
            continue
        ex = sig.nearest_claims(str(claim), sig.at[str(eid)], True, 3)
        base = ms.JUDGE_PROMPT.format(name=e['name'], note=e.get('note') or '(no note yet)',
                                      examples='\n'.join(f'- {c}' for c in ex) or '(none yet)', claim=claim)
        for who, role in READERS.items():
            h = ms.pair_hash(who, base)
            if h in done:
                continue
            r = rq.post(f'{OLLAMA_URL}/api/chat', timeout=300, json={
                'model': ms.JUDGE_MODEL, 'messages': [{'role': 'system', 'content': role}, {'role': 'user', 'content': base}],
                'think': False, 'stream': False, 'logprobs': True, 'top_logprobs': 10,
                'options': {'temperature': 0, 'num_predict': 1}})
            r.raise_for_status()
            yes = no = -math.inf
            for t in ((r.json().get('logprobs') or [{}])[0].get('top_logprobs') or []):
                w = t['token'].strip().lower()
                if w.startswith('yes'):
                    yes = max(yes, t['logprob'])
                elif w.startswith('no'):
                    no = max(no, t['logprob'])
            done[h] = 0.5 if yes == no == -math.inf else (1.0 if no == -math.inf else 0.0 if yes == -math.inf
                                                          else 1 / (1 + math.exp(no - yes)))
        if i % 40 == 0:
            with open(JURY + '.tmp', 'w') as f:
                json.dump(done, f)
            os.replace(JURY + '.tmp', JURY)
            print(f'jury {i}/{len(d["claims"])}', flush=True)
    with open(JURY + '.tmp', 'w') as f:
        json.dump(done, f)
    os.replace(JURY + '.tmp', JURY)
    return done, sig, index


def jury_features(done, sig, index):
    d = np.load(PAIRS)
    rows = []
    for claim, eid in zip(d['claims'], d['motifs']):
        e = index['entries'].get(str(eid))
        if e is None or str(eid) not in sig.at:
            rows.append([0.5] * len(READERS))
            continue
        ex = sig.nearest_claims(str(claim), sig.at[str(eid)], True, 3)
        base = ms.JUDGE_PROMPT.format(name=e['name'], note=e.get('note') or '(no note yet)',
                                      examples='\n'.join(f'- {c}' for c in ex) or '(none yet)', claim=claim)
        rows.append([done.get(ms.pair_hash(w, base), 0.5) for w in READERS])
    J = fc.logit(np.array(rows))
    return np.column_stack([J, J.mean(1), J.std(1)])


def report(label, X, y, g):
    t = fc.evaluate(X, y, list(g))
    t.pop('p')
    at95 = max((r['of kept'] for r in t['thresholds'] if r['precision'] and r['precision'] >= 0.95 and r['passes'] >= 20),
               default=0)
    print(f"{label}: AUC {t['auc']}; kept passable at 95% precision {at95:.0%}", flush=True)


def simulate(X, y, g, start=50, step=25, reps=5):
    """Held-out AUC as decisions come in, for each order of asking"""
    rng = np.random.default_rng(11)
    claims = np.unique(g)
    curves = defaultdict(list)
    for _ in range(reps):
        test_claims = set(rng.permutation(claims)[:len(claims) // 4])
        te = np.array([c in test_claims for c in g])
        pool = np.flatnonzero(~te)
        for order in ('random', 'likeliest first', 'least certain first'):
            known = list(rng.choice(pool, start, replace=False))
            curve = []
            while len(known) < len(pool):
                m, mu, sd = fc._fit(X[known], y[known])
                curve.append((len(known), roc_auc_score(y[te], m.predict_proba((X[te] - mu) / sd)[:, 1])))
                left = np.setdiff1d(pool, known)
                p = m.predict_proba((X[left] - mu) / sd)[:, 1]
                pick = (rng.permutation(left)[:step] if order == 'random' else
                        left[np.argsort(-p)[:step]] if order == 'likeliest first' else left[np.argsort(np.abs(p - 0.5))[:step]])
                known += list(pick)
            curves[order].append(curve)
    for order, cs in curves.items():
        n = min(len(c) for c in cs)
        pts = [(cs[0][i][0], np.mean([c[i][1] for c in cs])) for i in range(0, n, 4)]
        print(f'E6 {order}: ' + ', '.join(f'{k}: {a:.3f}' for k, a in pts), flush=True)


if __name__ == '__main__':
    if not os.path.exists(PAIRS):
        build_pairs()
    d = np.load(PAIRS)
    X, y, g = d['X'], d['y'], d['g']
    simulate(X, y, g)
    done, sig, index = ask_jury()
    J = jury_features(done, sig, index)
    report('E4 base', X, y, g)
    report('E4 + jury of three', np.hstack([X, J]), y, g)
    print('DONE', flush=True)
