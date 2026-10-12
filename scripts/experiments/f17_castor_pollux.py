"""F17 Castor and Pollux (Oct 12, from Fable's review): the checker's "might fit better" suggestions were ranked by the
plain six-fact weights (filing_confidence.Scorer.candidates) while filing uses the learned shortlist. Here both
rankings, held out by claim as Thumbelina measures them (no one-claim leak), on the motifs the person added by hand
("also", a move's target, a hand filing) in D5's Oct 10 cache: recall at 8 / 12 / 40 with the paired bootstrap
interval, and how much the two top 12s differ. No model asked. Paper: maudlin-data/papers/castor-and-pollux.md."""
import json
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402
from f15_thumbelina import D5, ranks  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import filing_confidence as fc  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402

OUT = os.path.join(harness.EXP, 'f17_castor_pollux.json')
KS = (8, 12, 40)


def hand_added() -> set:
    """(claim key, motif id) the person put a claim in by hand: 'also', a move's target, a hand filing (log, read only)"""
    out = set()

    def walk(a):
        act = a.get('action')
        if act in ('also', 'move') and a.get('claim') and a.get('target'):
            out.add((mi.key(a['claim']), a['target']))
        elif act == 'file' and a.get('claim') and a.get('id'):
            out.add((mi.key(a['claim']), a['id']))
        elif act == 'batch':
            for step in a.get('steps') or []:
                if isinstance(step, dict):
                    walk(step)
    for r in fc.log_rows():
        if isinstance(r.get('action'), dict):
            walk(r['action'])
    return out


def main():
    with open(D5, 'rb') as f:
        data = pickle.load(f)
    have = next(iter(data['claims'].values()))['signals']
    learned_feats = [f for f in harness.BASE if f in have]
    plain_feats = [f'facts:{f}' for f in mr.FACTS]
    hand = {(k, m) for k, m in hand_added() if k in data['claims'] and m in data['claims'][k]['truth']}
    print(f'{len(hand)} hand-added filings in the cache, on {len({k for k, _ in hand})} claims', flush=True)
    rk = {name: ranks(data, feats, drop_empty=True, floor=False)[0]
          for name, feats in (('plain', plain_feats), ('learned', learned_feats))}
    at, keys = data['at'], sorted({k for k, _ in hand})
    n = np.array([sum(1 for kk, _ in hand if kk == k) for k in keys], float)
    hits = {name: np.array([[sum(1 for kk, m in hand if kk == k and r[k][at[m]] < K) for K in KS] for k in keys], float)
            for name, r in rk.items()}
    rng = np.random.default_rng(0)
    diffs = []
    for _ in range(harness.BOOTS):
        pick = rng.integers(0, len(keys), len(keys))
        diffs.append((hits['learned'][pick].sum(0) - hits['plain'][pick].sum(0)) / n[pick].sum())
    lo, hi = np.percentile(diffs, [2.5, 97.5], axis=0)
    result = {'hand-added filings': len(hand), 'claims': len(keys)}
    for i, K in enumerate(KS):
        result[f'top {K}'] = {'plain': round(float(hits['plain'][:, i].sum() / n.sum()), 3),
                              'learned': round(float(hits['learned'][:, i].sum() / n.sum()), 3),
                              'gain interval': [round(float(lo[i]), 3), round(float(hi[i]), 3)]}
    # how much the twelve candidates change: per claim, the motifs it isn't in, best 12 by each ranking
    changed = []
    for k, c in data['claims'].items():
        tops = []
        for name in ('plain', 'learned'):
            r = rk[name][k]
            order = [m for m in np.argsort(r) if r[m] < len(data['ids']) and data['ids'][m] not in c['truth']]
            tops.append(set(order[:12]))
        changed.append(12 - len(tops[0] & tops[1]))
    result['of the 12 candidates, changed per claim'] = {'mean': round(float(np.mean(changed)), 2),
                                                         'median': float(np.median(changed))}
    with open(OUT, 'w') as f:
        json.dump(result, f, indent=1)
    line = (f"F17 hand-added motifs ({len(hand)}): " + '; '.join(
        f"top-{K} plain {result[f'top {K}']['plain']:.1%} -> learned {result[f'top {K}']['learned']:.1%} "
        f"({result[f'top {K}']['gain interval'][0]:+.1%} to {result[f'top {K}']['gain interval'][1]:+.1%})" for K in KS)
        + f"; candidates changed per claim {result['of the 12 candidates, changed per claim']['mean']} of 12")
    print(line, flush=True)
    harness.note(line)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
