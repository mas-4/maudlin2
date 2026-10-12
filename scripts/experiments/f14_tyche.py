"""F14 Tyche (Oct 12, from Fable's review, finding 5b): how much of a gain is chance? The harness now gives every
recall figure a 95% bootstrap interval (claims resampled 200 times) and every gain the interval of the paired
difference. Here the Oct 8-10 decisions are read again in that light, from caches only (no model asked; anything not
cached is reported, not embedded):

- on Oct 8's cache (signals.pkl, 428 claims), as first run: the Pleiades (bundles), Babel's pair (Qwen3-Embedding 8B
  and Arctic 2, from their saved vectors), Matryoshka (Gemma's cached layers, if their mxbai vectors are cached);
- on Oct 10's cache (signals_d5.pkl, 971 claims, every production signal): each kept signal taken out of the full
  weighting in turn (Lethe's news signals, Matryoshka's layers, Babel's embedders);
- Lethe on Oct 8's cache with the news directions production saved today (Oct 8's snapshot of headlines is gone).
Paper: maudlin-data/papers/tyche.md."""
import hashlib
import json
import os
import pickle
import sqlite3
import sys
from collections import Counter

import numpy as np

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

OUT = os.path.join(harness.EXP, 'f14_tyche.json')
D5 = os.path.join(harness.EXP, 'signals_d5.pkl')
MXBAI_CACHE = os.path.join(Config.data, 'narratives', 'embeddings.sqlite')


class Missing(Exception):
    """A vector not in any cache: computing it would need the GPU"""


def babel_cached(model: str, texts: list[str]) -> np.ndarray:
    """Babel's saved vectors for `texts`, never Ollama"""
    path = os.path.join(harness.EXP, 'embedders', model.replace(':', '_').replace('/', '_') + '.npz')
    cache = np.load(path, allow_pickle=True)['c'].item()
    gone = [t for t in texts if t not in cache]
    if gone:
        raise Missing(f'{model}: {len(set(gone))} of {len(set(texts))} texts not in its saved vectors')
    return np.stack([cache[t] for t in texts])


class MxbaiCached:
    """narratives.embed's vectors read from its cache file (read only), never Ollama"""

    def __init__(self):
        self.con = sqlite3.connect(f'file:{MXBAI_CACHE}?mode=ro', uri=True)

    def __call__(self, texts: list[str]) -> np.ndarray:
        keys = [hashlib.sha1(f'mxbai-embed-large\n{t}'.encode()).hexdigest() for t in texts]
        found = {}
        uniq = list(dict.fromkeys(keys))
        for i in range(0, len(uniq), 500):
            chunk = uniq[i:i + 500]
            found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in self.con.execute(
                f"SELECT key, v FROM vec WHERE key IN ({','.join('?' * len(chunk))})", chunk)})
        gone = [k for k in uniq if k not in found]
        if gone:
            raise Missing(f'mxbai: {len(gone)} of {len(uniq)} texts no longer in the embedder\'s cache')
        return np.stack([found[k] for k in keys])


def pleiades(data: dict):
    """The bundles signal exactly as e3_e5_bundles_graph.py makes it"""
    ids, at = data['ids'], data['at']
    truths = {k: c['truth'] for k, c in data['claims'].items()}
    pair, single = Counter(), Counter()
    for t in truths.values():
        for a in t:
            single[a] += 1
            for b in t:
                if a != b:
                    pair[(a, b)] += 1

    def bundles(d, k):
        own = truths[k]
        out = np.zeros(len(ids))
        for a in [ids[i] for i in np.argsort(-d['claims'][k]['signals']['today'])[:3]]:
            na = single[a] - (a in own)
            if na <= 0:
                continue
            for b in ids:
                if b != a:
                    c = pair[(a, b)] - (a in own and b in own)
                    if c > 0:
                        out[at[b]] += c / (na + 1)
        return out
    return {'bundles': bundles}


def babel(data: dict):
    import e11_embedders as e11
    e11.embed = babel_cached  # Babel's own signals, from its saved vectors only
    return {**e11.signals('qwen3-embedding:8b', data), **e11.signals('snowflake-arctic-embed2', data)}


def matryoshka(data: dict):
    from e2_e7_imagined_layers import GENRE_LAYER, LAYER_NAMES, LAYERED, read
    layers = read(LAYERED)
    ids = data['ids']
    vec = MxbaiCached()
    notes = vec([data['entries'][m].get('note') or data['entries'][m]['name'] for m in ids])
    texts = list(dict.fromkeys(t for ls in layers.values() for t in ls.values() if t and t.strip().lower() != 'none'))
    V = dict(zip(texts, vec(texts)))
    genre_layer = [GENRE_LAYER.get(mi.genre_of(data['entries'][m]) or '') for m in ids]

    def sims(k):
        ls = layers.get(k) or {}
        return {n: (notes @ V[ls[n]] if ls.get(n) and ls[n].strip().lower() != 'none' else np.full(len(ids), -1.0))
                for n in LAYER_NAMES}

    def best(d, k):
        return np.max(np.stack(list(sims(k).values())), 0)

    def genre(d, k):
        s = sims(k)
        return np.array([s[g][i] if g else -1.0 for i, g in enumerate(genre_layer)])
    return {'layers best': best, 'layer of its genre': genre}


def lethe(data: dict):
    """Lethe's two signals as e1_news.py made them (40 directions), but from the news directions production saved today
    (motifs/news_directions.npz): Oct 8's snapshot of headlines is gone"""
    from app.analysis.motif_signals import NEWS
    d = np.load(NEWS)
    mu, U = d['center'], d['directions']
    ids, entries = data['ids'], data['entries']
    vec = MxbaiCached()

    def out(V):
        W = (V - mu) - ((V - mu) @ U.T) @ U
        return W / np.linalg.norm(W, axis=-1, keepdims=True)
    notes = out(vec([entries[m].get('note') or entries[m]['name'] for m in ids]))
    member = {m: [c['claim'] for c in entries[m]['claims']] for m in ids}
    allc = list(dict.fromkeys(c for cs in member.values() for c in cs))
    C = dict(zip(allc, out(vec(allc))))
    keys = list(data['claims'])
    Q = dict(zip(keys, out(vec([data['claims'][k]['claim'] for k in keys]))))

    def note(d, key):
        return notes @ Q[key]

    def near(d, key):
        mine = mi.key(d['claims'][key]['claim'])
        return np.array([max((float(C[c] @ Q[key]) for c in member[m] if mi.key(c) != mine), default=-1.0) for m in ids])
    return {'note minus news': note, 'nearest minus news': near}


def cached(names: list[str]):
    """Signals already in the cache, as `extra` functions (so they can be taken out of the base and added back)"""
    def one(n):
        return lambda d, k: d['claims'][k]['signals'][n]
    return {n: one(n) for n in names}


def main(only: list[str]):
    try:
        with open(OUT) as f:
            results = json.load(f)
    except (OSError, ValueError):
        results = {}
    oct8 = harness.load()
    print(f'Oct 8 cache: {len(oct8["claims"])} claims, {len(oct8["ids"])} motifs', flush=True)
    for name, make in [('Pleiades', pleiades), ('Babel pair', babel), ('Matryoshka', matryoshka),
                       ("Lethe, today's news directions", lethe)]:
        if only and name.split(',')[0] not in only:
            continue
        try:
            extra = make(oct8)
            results[f'oct8 {name}'] = harness.evaluate(oct8, extra, label=f'F14 Oct 8 as first run: {name}')
        except Missing as e:
            print(f'F14 Oct 8 {name}: not rerun, {e} (the GPU would be needed)', flush=True)
            results[f'oct8 {name}'] = {'not rerun': str(e)}
    if not only or 'folds' in only:  # the noise the bootstrap leaves out: another split of the claims into folds
        for name, make in [('Pleiades', pleiades), ('Matryoshka', matryoshka)]:
            extra, gains = make(oct8), []
            for seed in range(1, 6):
                b = harness.recall(oct8, harness.ranks(oct8, seed=seed))
                n = harness.recall(oct8, harness.ranks(oct8, extra, seed=seed))
                gains.append({str(K): round(n[K] - b[K], 3) for K in (8, 12, 40)} | {'base 12': b[12]})
            results[f'oct8 {name} other fold splits'] = {'gains': gains}
            line = (f'F14 Oct 8 {name}, five other fold splits: top-12 base ' + ', '.join(f"{g['base 12']:.1%}" for g in gains)
                    + '; gain ' + ', '.join(f"{g['12']:+.1%}" for g in gains))
            print(line, flush=True)
            harness.note(line)
    if only and 'oct10' not in only:
        return save(results)
    with open(D5, 'rb') as f:
        oct10 = pickle.load(f)
    have = next(iter(oct10['claims'].values()))['signals']
    full = [f for f in harness.BASE if f in have]
    print(f'Oct 10 cache: {len(oct10["claims"])} claims, {len(oct10["ids"])} motifs, {len(full)} signals', flush=True)
    for name, group in [('Lethe', ['news out note', 'news out near']),
                        ('Matryoshka', ['layers best', 'layer of its genre']),
                        ('Babel', ['qwen3 8b note', 'qwen3 8b near', 'arctic2 note', 'arctic2 near'])]:
        rest = [f for f in full if f not in group]
        results[f'oct10 {name}'] = harness.evaluate(oct10, cached(group), feats=rest,
                                                    label=f'F14 Oct 10, taken out then added back: {name}')
    save(results)


def save(results: dict):
    with open(OUT, 'w') as f:
        json.dump({k: {a: ({str(K): v for K, v in b.items()} if isinstance(b, dict) else b) for a, b in r.items()}
                   for k, r in results.items()}, f, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main(sys.argv[1:])  # parts by name (Pleiades, Babel pair, Matryoshka, Lethe, folds, oct10); none: all
