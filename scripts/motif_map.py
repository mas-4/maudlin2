"""The motif map (Oct 30; the person: "it would be cool to have a way to just visualize embedding space of these motif
systems"): every live motif's centre (the mean of its confirmed claims, as the shortlist's "center of claims" and the
Hestia experiment take it) and every filed claim, laid out in two dimensions by t-SNE, once per space: Qwen3-Embedding
8B, mxbai (production's) and TF-IDF words. The page beside this script (motif_map.html) draws it: pan and zoom, a
motif's claims tied to its centre, its nearest centres, its related and rests-on links, genres and groups to pick out.

Vectors come from the embedding cache only; no model is asked. A claim missing from the cache is left off the map.

    motif_map.py OUT_DIR      writes OUT_DIR/map.json, and OUT_DIR/index.html: the page with the data in it"""
import hashlib
import json
import os
import sqlite3
import sys
import time
from datetime import datetime as dt

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from app.analysis import local_models as lm  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

CACHE = os.path.join(Config.data, 'narratives', 'embeddings.sqlite')
SPACES = {'qwen3 8b': lm.QWEN3_EMBED, 'mxbai': lm.MXBAI, 'tfidf': None}
NEAR = 8  # nearest centres listed for each motif


def lit(v):
    """A field as saved: some copies keep lists and dicts as their Python text"""
    if isinstance(v, str) and v[:1] in '[{':
        import ast
        try:
            return ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    return v


def cached(model: str, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Unit vectors for texts from the cache, and which were there"""
    keys = [hashlib.sha1(f'{model}\n{t}'.encode()).hexdigest() for t in texts]
    con = sqlite3.connect(f'file:{CACHE}?mode=ro', uri=True, timeout=120)
    found = {}
    for i in range(0, len(keys), 500):
        chunk = keys[i:i + 500]
        found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in con.execute(
            f"SELECT key, v FROM vec WHERE key IN ({','.join('?' * len(chunk))})", chunk)})
    con.close()
    dim = len(next(iter(found.values())))
    X = np.zeros((len(texts), dim))
    have = np.zeros(len(texts), dtype=bool)
    for i, k in enumerate(keys):
        if k in found:
            X[i], have[i] = found[k], True
    return X, have


def tfidf(texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    T = TfidfVectorizer(stop_words='english', sublinear_tf=True, ngram_range=(1, 2), min_df=2).fit_transform(texts)
    have = np.asarray(T.multiply(T).sum(1)).ravel() > 0
    X = TruncatedSVD(200, random_state=0).fit_transform(T)  # words in 200 directions, enough for t-SNE's neighbours
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
    return X, have


def layout(P: np.ndarray) -> np.ndarray:
    """2-D t-SNE of unit vectors (cosine), scaled to 0..1000"""
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    Z = PCA(min(50, P.shape[1]), random_state=0).fit_transform(P)
    Y = TSNE(2, metric='cosine', init='pca', perplexity=30, random_state=0).fit_transform(Z)
    Y -= Y.min(0)
    return Y / Y.max() * 1000


def build(out: str):
    t0 = time.time()
    index = mi.load()
    live = mi.live(index)
    genres = (index.get('facet_values') or {}).get('genre', [])
    groups = {g: v.get('name', g) for g, v in (index.get('groups') or {}).items()}
    related = [tuple(p) for p in index.get('related', []) if len(p) == 2]
    texts, at = [], {}
    for e in live:
        for c in lit(e.get('claims')) or []:
            if isinstance(c, dict) and c.get('claim') and c['claim'] not in at:
                at[c['claim']] = len(texts)
                texts.append(c['claim'])
    motifs, members = [], []
    for e in live:
        cl = [c for c in (lit(e.get('claims')) or []) if isinstance(c, dict) and c.get('claim')]
        if not cl:
            continue
        facets = lit(e.get('facets'))
        motifs.append({'id': e['id'], 'name': e['name'], 'note': e.get('note') or '',
                       'genre': facets.get('genre') if isinstance(facets, dict) else None,
                       'groups': list(lit(e.get('groups')) or []), 'rests': list(lit(e.get('parents')) or []),
                       'done': bool(lit(e.get('done')))})
        members.append([(at[c['claim']], c.get('checked') == 'yes') for c in cl])
    row = {m['id']: i for i, m in enumerate(motifs)}
    print(f'{len(motifs)} motifs with claims, {len(texts)} claims', flush=True)

    claim_xy = {t: {} for t in range(len(texts))}
    claim_d = {}
    for space, model in SPACES.items():
        X, have = tfidf(texts) if model is None else cached(model, texts)
        C, cn, keep = [], [], []
        for i, mem in enumerate(members):
            use = [t for t, ok in mem if ok and have[t]] or [t for t, _ in mem if have[t]]  # confirmed, else all
            if not use:
                continue
            s = X[use].sum(0)
            C.append(s / max(np.linalg.norm(s), 1e-12))
            cn.append(len(use))
            keep.append(i)
        C = np.array(C)
        ok = np.where(have)[0]
        Y = layout(np.vstack([X[ok], C]))
        for j, t in enumerate(ok):
            claim_xy[t][space] = [round(float(Y[j, 0]), 1), round(float(Y[j, 1]), 1)]
        for j, i in enumerate(keep):
            motifs[i].setdefault('xy', {})[space] = [round(float(Y[len(ok) + j, 0]), 1), round(float(Y[len(ok) + j, 1]), 1)]
        # nearest centres, and each claim's likeness to its motifs' centres (itself left out when it is one of them)
        S = C @ C.T
        np.fill_diagonal(S, -2)
        for j, i in enumerate(keep):
            near = np.argsort(-S[j])[:NEAR]
            motifs[i].setdefault('near', {})[space] = [[keep[k], round(float(S[j, k]), 3)] for k in near]
        if space == 'qwen3 8b':
            sums = {i: X[[t for t, ok_ in members[i] if ok_ and have[t]] or [t for t, _ in members[i] if have[t]]].sum(0)
                    for i in keep}
            for i in keep:
                inside = {t for t, ok_ in members[i] if ok_ and have[t]} or {t for t, _ in members[i] if have[t]}
                for t, _ in members[i]:
                    if not have[t]:
                        continue
                    s = sums[i] - X[t] if t in inside else sums[i]
                    if t in inside and len(inside) == 1:
                        continue
                    claim_d[t, i] = round(float(X[t] @ s / max(np.linalg.norm(s), 1e-12)), 3)
            for i in keep:
                motifs[i]['spread'] = round(float(np.mean([claim_d[t, i] for t, _ in members[i] if (t, i) in claim_d]))
                                            if any((t, i) in claim_d for t, _ in members[i]) else -1, 3)
        print(f'{space}: {len(ok)} claims, {len(keep)} centres laid out ({time.time() - t0:.0f} s)', flush=True)

    of = {t: [] for t in range(len(texts))}
    for i, mem in enumerate(members):
        for t, ok_ in mem:
            of[t].append([i, int(ok_), claim_d.get((t, i))])
    data = {
        'built': dt.now().isoformat(timespec='minutes'), 'spaces': list(SPACES), 'genres': genres, 'groups': groups,
        'related': [[row[a], row[b]] for a, b in related if a in row and b in row],
        'motifs': [{**m, 'rests': [row[p] for p in m['rests'] if p in row]} for m in motifs],
        'claims': [{'t': texts[t], 'xy': claim_xy[t], 'm': of[t]} for t in range(len(texts)) if claim_xy[t]],
    }
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'map.json'), 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'motif_map.html')) as f:
        page = f.read()
    with open(os.path.join(out, 'index.html'), 'w') as f:  # one file: the data rides in the page
        f.write(page.replace('__MAP_DATA__', json.dumps(data, separators=(',', ':')).replace('</', '<\\/')))
    print(f'wrote {out}/map.json ({os.path.getsize(os.path.join(out, "map.json")) / 1e6:.1f} MB) in {time.time() - t0:.0f} s')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    build(sys.argv[1])
