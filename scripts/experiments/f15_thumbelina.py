"""F15 Thumbelina (Oct 12, from Fable's review, "The shortlist"): does the shortlist serve the small motifs? Held-out
recall at 8 / 12 / 40 of the production learned shortlist on the person's confirmed filings, by the size of the motif
(1, 2, 3-5, 6-10, 11+ claims); how many of those filings fall under the alike floor (motif_index.SHOWN_FLOOR on the
three plain likenesses), which removes a motif before the weights see it; and how much of the held-out figure is a
leak: held out, a one-claim motif is left with no claims, a look no other motif in the test has, so "no claims left"
marks the answer. From D5's Oct 10 cache (every production signal), no model asked. Paper:
maudlin-data/papers/thumbelina.md."""
import json
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'f15_thumbelina.json')
D5 = os.path.join(harness.EXP, 'signals_d5.pkl')
BANDS = [('1', 1, 1), ('2', 2, 2), ('3-5', 3, 5), ('6-10', 6, 10), ('11+', 11, 10 ** 9)]
KS = (8, 12, 40)
LIKENESS = ['facts:text', 'facts:name and note', 'facts:nearest claim']


def band_of(n: int) -> str:
    return next(b for b, lo, hi in BANDS if lo <= n <= hi)


def ranks(data: dict, feats: list[str], drop_empty: bool, floor: bool, folds: int = 5):
    """harness.ranks, with motifs left empty by holding the claim out dropped from training and ranking
    (drop_empty), and motifs under the alike floor given no rank (floor). Unranked: rank len(ids). Also the weights
    learned on every claim, standardized as production keeps them"""
    from sklearn.linear_model import LogisticRegression
    keys = sorted(data['claims'])
    n = len(data['ids'])

    def matrix(k):
        s = data['claims'][k]['signals']
        X = np.column_stack([s[f] for f in feats])
        y = np.array([m in data['claims'][k]['truth'] for m in data['ids']])
        empty = s['facts:nearest claim'] <= -1.0  # no claim left in the motif once this one is held out
        under = np.max(np.stack([s[f] for f in LIKENESS]), 0) < mi.SHOWN_FLOOR
        return X, y, empty, under

    rows = {k: matrix(k) for k in keys}

    def fit(ks):
        X = np.concatenate([rows[k][0][~rows[k][2]] if drop_empty else rows[k][0] for k in ks])
        y = np.concatenate([rows[k][1][~rows[k][2]] if drop_empty else rows[k][1] for k in ks])
        mu, sd = X.mean(0), X.std(0) + 1e-9
        return LogisticRegression(max_iter=3000, class_weight='balanced', C=0.5).fit((X - mu) / sd, y), mu, sd

    out = {}
    for f in range(folds):
        test = set(keys[f::folds])
        model, mu, sd = fit([k for k in keys if k not in test])
        for k in test:
            X, _, empty, under = rows[k]
            s = model.decision_function((X - mu) / sd)
            gone = (empty if drop_empty else np.zeros(n, bool)) | (under if floor else np.zeros(n, bool))
            s = np.where(gone, -np.inf, s)
            r = np.argsort(np.argsort(-s))
            out[k] = np.where(gone, n, r)
    model, _, _ = fit(keys)
    return out, dict(zip(feats, model.coef_[0].round(3).tolist()))


def by_band(data: dict, rk: dict, size: dict, boots: int = harness.BOOTS) -> dict:
    """Recall at each K by size band, with its bootstrap interval (claims resampled)"""
    at = data['at']
    keys = sorted(rk)
    out = {}
    for b, _, _ in BANDS + [('all', 0, 0)]:
        n = np.array([sum(1 for m in data['claims'][k]['truth'] if b == 'all' or band_of(size[m]) == b) for k in keys], float)
        h = np.array([[sum(1 for m in data['claims'][k]['truth'] if (b == 'all' or band_of(size[m]) == b) and rk[k][at[m]] < K)
                       for K in KS] for k in keys], float)
        if not n.sum():
            continue
        rng = np.random.default_rng(0)
        draws = []
        for _ in range(boots):
            pick = rng.integers(0, len(keys), len(keys))
            draws.append(h[pick].sum(0) / max(n[pick].sum(), 1))
        lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)
        out[b] = {'filings': int(n.sum()), **{str(K): round(float(h[:, i].sum() / n.sum()), 3) for i, K in enumerate(KS)},
                  **{f'{K} interval': [round(float(lo[i]), 3), round(float(hi[i]), 3)] for i, K in enumerate(KS)}}
    return out


def main():
    with open(D5, 'rb') as f:
        data = pickle.load(f)
    have = next(iter(data['claims'].values()))['signals']
    feats = [f for f in harness.BASE if f in have]
    size = {m: len({mi.key(c['claim']) for c in data['entries'][m]['claims']}) for m in data['ids']}
    print(f"Oct 10 cache: {len(data['claims'])} claims, {len(data['ids'])} motifs, {len(feats)} signals", flush=True)
    result = {'claims': len(data['claims']), 'motifs': len(data['ids'])}
    # the floor: how many of the person's filings it removes before the weights see them, by band
    under = {b: [0, 0] for b, _, _ in BANDS}
    for k, c in data['claims'].items():
        s = c['signals']
        best = np.max(np.stack([s[f] for f in LIKENESS]), 0)
        for m in c['truth']:
            under[band_of(size[m])][1] += 1
            under[band_of(size[m])][0] += int(best[data['at'][m]] < mi.SHOWN_FLOOR)
    total = sum(v[1] for v in under.values())
    result['under the floor'] = {b: {'under': u, 'of': t} for b, (u, t) in under.items()}
    line = (f"F15 alike floor: {sum(v[0] for v in under.values())} of {total} confirmed filings under it; by band "
            + ', '.join(f'{b}: {u} of {t}' for b, (u, t) in under.items()))
    print(line, flush=True)
    harness.note(line)
    motifs_by_band = {b: sum(1 for m in data['ids'] if band_of(size[m]) == b) for b, _, _ in BANDS}
    result['motifs by band'] = motifs_by_band
    for name, drop_empty, floor in [('production', False, False), ('production, floor applied', False, True),
                                    ('leak removed', True, False), ('leak removed, floor applied', True, True)]:
        rk, coef = ranks(data, feats, drop_empty, floor)
        bands = by_band(data, rk, size)
        result[name] = {'by band': bands, 'weights': coef}
        if not floor:  # the filings under the floor: how many the weights would have put in the top 12 without it
            lost = {b: 0 for b, _, _ in BANDS}
            for k, c in data['claims'].items():
                best = np.max(np.stack([c['signals'][f] for f in LIKENESS]), 0)
                for m in c['truth']:
                    lost[band_of(size[m])] += int(best[data['at'][m]] < mi.SHOWN_FLOOR and rk[k][data['at'][m]] < 12)
            result[name]['under the floor, in the top 12 without it'] = lost
            print(f'F15 {name}: under the floor but in the top 12 without it, by band {lost}', flush=True)
        line = (f'F15 {name}: top-12 ' + '; '.join(f"{b} {v['12']:.1%} ({v['filings']})" for b, v in bands.items())
                + f"; top-8 all {bands['all']['8']:.1%}, top-40 all {bands['all']['40']:.1%}; weight on nearest claim "
                f"{coef['facts:nearest claim']:+.2f}")
        print(line, flush=True)
        harness.note(line)
    with open(OUT, 'w') as f:
        json.dump(result, f, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
