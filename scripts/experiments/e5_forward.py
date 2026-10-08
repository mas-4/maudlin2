"""E5 tested forward (docs/filing-experiments.md): the spread over the person's links helped held out, but the links
were partly made from the same filings, and a strict test by date had too little to go on. So: for each new claim
nobody has said yes to yet, log its ranking of the motifs now, by the learned weighting with and without the spread
(the links as they stand today, the claim held out of the motifs the model put it in); once the person has checked
it, see which ranking had their motifs higher.

    python scripts/experiments/e5_forward.py log      # in a GPU window: new claims' shapes and embeddings
    python scripts/experiments/e5_forward.py score    # any time: the claims the person has checked since"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402

LOG = os.path.join(harness.EXP, 'e5_forward.jsonl')
TOP = 40


def links(index: dict) -> dict:
    out = defaultdict(set)
    for e in index['entries'].values():
        for p in mi.parents_of(e):
            out[e['id']].add(p)
            out[p].add(e['id'])
    for a, b in index.get('related', []):
        out[a].add(b)
        out[b].add(a)
    return out


def spread(today: np.ndarray, ids: list[str], at: dict, near: dict) -> np.ndarray:
    """Each motif's best neighbour's score (today's shortlist, as z-scores) through the links (E5's best variant)"""
    z = (today - today.mean()) / (today.std() + 1e-9)
    out = np.full(len(ids), -3.0)
    for m in ids:
        vals = [z[at[n]] for n in near.get(m, ()) if n in at]
        if vals:
            out[at[m]] = max(vals)
    return out


def weighting(data: dict, feats: list[str], with_spread: bool):
    """The learned weighting on the person's confirmed claims (the harness's, all of them at once)"""
    from sklearn.linear_model import LogisticRegression
    near = links(mi.load())
    X, y = [], []
    for c in data['claims'].values():
        cols = [c['signals'][f] for f in feats]
        if with_spread:
            cols.append(spread(c['signals']['today'], data['ids'], data['at'], near))
        X.append(np.column_stack(cols))
        y.append([m in c['truth'] for m in data['ids']])
    X, y = np.concatenate(X), np.concatenate(y)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    return LogisticRegression(max_iter=3000, class_weight='balanced', C=0.5).fit((X - mu) / sd, y), mu, sd


def said_yes(index: dict) -> dict:
    """Claim key -> the person's motifs for it (their done motifs where it's checked yes)"""
    out = defaultdict(set)
    for e in mi.live(index):
        if e.get('done'):
            for c in e['claims']:
                if c.get('checked') == 'yes':
                    out[mi.key(c['claim'])].add(e['id'])
    return out


def logged() -> list[dict]:
    try:
        with open(LOG) as f:
            return [json.loads(x) for x in f if x.strip()]
    except OSError:
        return []


def log():
    data = harness.load()
    index = mi.load()
    sig = ms.Signals(index)
    have = next(iter(data['claims'].values()))['signals']
    feats = [f for f in harness.BASE if f in have]
    models = {w: weighting(data, feats, w) for w in (False, True)}
    yes = said_yes(index)
    done = {r['key'] for r in logged()}
    new = list(dict.fromkeys(x['claim'] for x in mi.to_check()
                             if mi.key(x['claim']) not in yes and mi.key(x['claim']) not in done))
    if not new:
        print('E5 forward: nothing new to log', flush=True)
        return
    sig.prepare(new)
    w = mr.weights()
    ids = [e['id'] for e in sig.entries]
    at = sig.at
    near = links(index)
    with open(LOG, 'a') as f:
        for claim in new:
            s = sig.cheap(claim, leave_out=True)
            F = mr.facts(sig.entries, claim, sig.vec, leave_out=True)
            s['today'] = F @ np.array([w['weights'][x] for x in mr.FACTS]) + w['bias']
            for j, x in enumerate(mr.FACTS):
                s[f'facts:{x}'] = F[:, j]
            row = {'key': mi.key(claim), 'claim': claim, 'at': datetime.now().isoformat(timespec='seconds'),
                   'links': sum(len(v) for v in near.values()) // 2}
            for with_spread, (m, mu, sd) in models.items():
                X = np.column_stack([s[x] for x in feats] + ([spread(s['today'], ids, at, near)] if with_spread else []))
                order = np.argsort(-m.decision_function((X - mu) / sd))[:TOP]
                row['spread' if with_spread else 'base'] = [ids[i] for i in order]
            f.write(json.dumps(row) + '\n')
    sig.save()
    print(f'E5 forward: {len(new)} new claims logged', flush=True)


def score():
    yes = said_yes(mi.load())
    rows = [r for r in logged() if yes.get(r['key'])]
    if not rows:
        print('E5 forward: none of the logged claims checked yet', flush=True)
        return
    total = sum(len(yes[r['key']]) for r in rows)
    parts = []
    for kind in ('base', 'spread'):
        hits = {K: sum(len(yes[r['key']] & set(r[kind][:K])) for r in rows) for K in (8, 12, 40)}
        parts.append(f"{kind} top-8 {hits[8] / total:.1%}, top-12 {hits[12] / total:.1%}, top-40 {hits[40] / total:.1%}")
    line = f"E5 forward, {len(rows)} claims checked since logged ({total} of the person's motifs): " + '; '.join(parts)
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    {'log': log, 'score': score}[sys.argv[1] if len(sys.argv) > 1 else 'score']()
