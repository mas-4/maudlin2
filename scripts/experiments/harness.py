"""The filing experiments' common ground (docs/filing-experiments.md): the person's confirmed claims (truth), every
cheap signal against every motif for each (the claim held out of its motifs), and one way of scoring any new idea:
a weighting learned on the other claims (grouped folds), then how many of the person's motifs land in the top 8 / 12 /
20 / 40, and how many of the hard misses (outside today's top 40) it brings back. Every figure comes with its 95%
bootstrap interval (claims resampled 200 times), and every gain with the interval of the paired difference.

    from harness import load, evaluate
    data = load()                      # cached in maudlin-data/motifs/experiments
    evaluate(data, extra={'my idea': fn})   # fn(data, claim_key) -> np.ndarray over data['ids']

Built from the caches only (embeddings, shapes): no model is asked, so it runs at any time."""
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_retriever as mr  # noqa: E402
from app.analysis import motif_signals as ms  # noqa: E402
from app.utils import Config  # noqa: E402

EXP = os.path.join(Config.data, 'motifs', 'experiments')
CACHE = os.path.join(EXP, 'signals.pkl')
KS = (8, 12, 20, 40)
BASE = ['today'] + ms.CHEAP + [f'facts:{f}' for f in mr.FACTS]


def build(path: str = CACHE) -> dict:
    """Every cheap signal for every confirmed claim of the person's (in their done motifs), against every live motif"""
    index = mi.load()
    sig = ms.Signals(index)
    w = mr.weights()
    ids = [e['id'] for e in sig.entries]
    truth, text = {}, {}
    for e in sig.entries:
        if e.get('done'):
            for c in e['claims']:
                if c.get('checked') == 'yes':
                    truth.setdefault(mi.key(c['claim']), set()).add(e['id'])
                    text[mi.key(c['claim'])] = c['claim']
    sig.prepare(list(text.values()), ask=False)
    claims = {}
    for i, (k, claim) in enumerate(text.items()):
        s = sig.cheap(claim, leave_out=True, ask=False)
        F = mr.facts(sig.entries, claim, sig.vec, leave_out=True)
        s['today'] = F @ np.array([w['weights'][f] for f in mr.FACTS]) + w['bias']
        for j, f in enumerate(mr.FACTS):
            s[f'facts:{f}'] = F[:, j]
        claims[k] = {'claim': claim, 'truth': truth[k], 'signals': {n: np.asarray(v, dtype=np.float32) for n, v in s.items()}}
        if i % 100 == 0:
            print(f'signals {i}/{len(text)}', flush=True)
    data = {'ids': ids, 'at': {m: n for n, m in enumerate(ids)}, 'claims': claims,
            'entries': {e['id']: e for e in sig.entries}}
    os.makedirs(EXP, exist_ok=True)
    with open(path, 'wb') as f:
        pickle.dump(data, f)
    return data


def load(path: str = CACHE, rebuild: bool = False) -> dict:
    if rebuild or not os.path.exists(path):
        return build(path)
    with open(path, 'rb') as f:
        return pickle.load(f)


_memo = {}


def _matrix(data: dict, k: str, feats: list[str], extra: dict) -> np.ndarray:
    s = data['claims'][k]['signals']
    cols = [s[n] for n in feats]
    for fn in extra.values():  # each new signal worked out once per claim, not once per fold
        if (fn, k) not in _memo:  # the function itself, not its id: an id is reused once it's gone
            _memo[(fn, k)] = fn(data, k)
        cols.append(_memo[(fn, k)])
    return np.column_stack(cols)


def ranks(data: dict, extra: dict | None = None, feats: list[str] | None = None, folds: int = 5,
          seed: int | None = None) -> dict:
    """Each claim's ranking of every motif by a weighting learned on the other claims: {claim key: rank array}. With
    `seed`, the claims are dealt into folds in a shuffled order (the split's own noise)"""
    from sklearn.linear_model import LogisticRegression
    extra = extra or {}
    if feats is None:  # signals added since the cache was built (rebuild to have them) left out
        have = next(iter(data['claims'].values()))['signals']
        feats = [f for f in BASE if f in have]
    keys = sorted(data['claims'])
    if seed is not None:
        np.random.default_rng(seed).shuffle(keys)
    out = {}
    for f in range(folds):
        test = set(keys[f::folds])
        X = np.concatenate([_matrix(data, k, feats, extra) for k in keys if k not in test])
        y = np.concatenate([[m in data['claims'][k]['truth'] for m in data['ids']] for k in keys if k not in test])
        mu, sd = X.mean(0), X.std(0) + 1e-9
        model = LogisticRegression(max_iter=3000, class_weight='balanced', C=0.5).fit((X - mu) / sd, y)
        for k in test:
            s = model.decision_function((_matrix(data, k, feats, extra) - mu) / sd)
            out[k] = np.argsort(np.argsort(-s))
    return out


def recall(data: dict, rk: dict) -> dict:
    at = data['at']
    hits = dict.fromkeys(KS, 0)
    total = 0
    for k, r in rk.items():
        for m in data['claims'][k]['truth']:
            total += 1
            for K in KS:
                hits[K] += r[at[m]] < K
    return {K: round(hits[K] / total, 3) for K in KS}


def misses(data: dict, rk: dict, K: int = 40) -> set:
    at = data['at']
    return {(k, m) for k, r in rk.items() for m in data['claims'][k]['truth'] if r[at[m]] >= K}


BOOTS = 200  # Oct 12 (Fable's review, Tyche): every recall figure with a 95% interval, claims resampled


def _hits(data: dict, rk: dict, keys: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Per claim: how many of the person's motifs it has, and how many of them are in the top K, for each K"""
    at = data['at']
    n = np.array([len(data['claims'][k]['truth']) for k in keys], dtype=float)
    h = np.array([[sum(rk[k][at[m]] < K for m in data['claims'][k]['truth']) for K in KS] for k in keys], dtype=float)
    return n, h


def interval(data: dict, rk: dict, other: dict | None = None, boots: int = BOOTS, seed: int = 0) -> dict:
    """The 95% bootstrap interval of recall at each K: claims drawn with replacement `boots` times (a claim's motifs
    travel together), the ranks held fixed. With `other` (a second arm's ranks over the same claims), the interval of
    its recall minus this one's, on the same draws: {K: (low, high)}"""
    keys = sorted(rk)
    n, h = _hits(data, rk, keys)
    h2 = _hits(data, other, keys)[1] if other is not None else None
    rng = np.random.default_rng(seed)
    out = np.empty((boots, len(KS)))
    for b in range(boots):
        pick = rng.integers(0, len(keys), len(keys))
        tot = n[pick].sum()
        out[b] = (h2[pick].sum(0) - h[pick].sum(0)) / tot if h2 is not None else h[pick].sum(0) / tot
    lo, hi = np.percentile(out, [2.5, 97.5], axis=0)
    return {K: (round(float(lo[i]), 3), round(float(hi[i]), 3)) for i, K in enumerate(KS)}


def evaluate(data: dict, extra: dict | None = None, feats: list[str] | None = None, label: str = '',
             boots: int = BOOTS) -> dict:
    """The learned weighting with and without `extra` signals: recall at each K, and the hard misses brought back.
    Each recall with its 95% bootstrap interval over claims, and the gain with the interval of the paired difference
    (the same draws for both arms); boots=0 for none"""
    base = ranks(data, feats=feats)
    new = ranks(data, extra, feats=feats)
    b, n = recall(data, base), recall(data, new)
    mb, mn = misses(data, base), misses(data, new)
    out = {'label': label, 'base': b, 'with': n, 'misses before': len(mb), 'misses after': len(mn),
           'brought back': len(mb - mn), 'newly missed': len(mn - mb)}
    if boots:
        bi, ni, gi = interval(data, base, boots=boots), interval(data, new, boots=boots), interval(data, base, new, boots=boots)
        out.update({'base interval': bi, 'with interval': ni, 'gain interval': gi})

        def fig(K):
            return (f"top-{K} {b[K]:.1%} [{bi[K][0]:.1%}-{bi[K][1]:.1%}] -> {n[K]:.1%} [{ni[K][0]:.1%}-{ni[K][1]:.1%}] "
                    f"(gain {n[K] - b[K]:+.1%}, {gi[K][0]:+.1%} to {gi[K][1]:+.1%})")
    else:
        def fig(K):
            return f"top-{K} {b[K]:.1%} -> {n[K]:.1%}"
    line = (f"{label or 'experiment'}: {fig(12)}; {fig(8)}; {fig(40)}; "
            f"misses {len(mb)} -> {len(mn)} (back {len(mb - mn)}, new {len(mn - mb)})")
    print(line, flush=True)
    note(line)
    return out


def note(line: str):
    """A result kept in the experiments' own log too (results.log), whatever happens to the runner's output"""
    from datetime import datetime
    with open(os.path.join(EXP, 'results.log'), 'a') as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')} {line}\n")
    try:  # and into the catalog (catalog.py: experiments.sqlite)
        import catalog
        catalog.record(line)
    except Exception:  # noqa: BLE001 - the log line above stands
        pass


if __name__ == '__main__':
    d = load(rebuild=True)
    print(len(d['claims']), 'claims;', recall(d, ranks(d)))
