"""Motif space (Oct 30; the person: "it would be cool to have a way to just visualize embedding space of these motif
systems", then "we should make *this* public"): every motif's centre (the mean of its claims, as the shortlist's
"center of claims" and the Hestia experiment take it) and its claims, laid out in two dimensions by t-SNE, once per
space: Qwen3-Embedding 8B (meaning), mxbai (the filing's own centre) and TF-IDF (shared words).

Vectors come from the embedding cache only; no model is asked, nothing goes to the GPU, and a claim missing from the
cache is left off. A layout of 4,000 claims takes about 15 s a space on the CPU.

    layout(entries, spaces)   the drawing's data: motifs (with x, y per space, their nearest centres and how tight
                              their claims sit around the centre) and claims (x, y per space, their motifs)
    today(entries)            the public layer's layout, worked out once a day and kept (TODAY_FILE): the site's
                              motif space page and the front page's cloud of stories told read it

Used by app/site/page_motif_space.py (the public page, from the verified motifs and their screened claims only) and
scripts/motif_map.py (the person's own copy, every live motif and filing)."""
import hashlib
import json
import os
import sqlite3
import time
from datetime import date

import numpy as np

from app.analysis import local_models as lm
from app.utils import Config, get_logger

logger = get_logger(__name__)

CACHE = os.path.join(Config.data, 'narratives', 'embeddings.sqlite')
TODAY_FILE = os.path.join(Config.data, 'motifs', 'motif_space.json')
SPACES = {'qwen3 8b': lm.QWEN3_EMBED, 'mxbai': lm.MXBAI, 'tfidf': None}
PUBLIC_SPACES = ('qwen3 8b', 'tfidf')
NEAR = 8  # nearest centres kept for each motif
VERSION = 3  # of the kept layout: a new one (Oct 30: regions) is worked out again the same day


def cached(model: str, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Unit vectors for texts from the embedding cache, and which were there"""
    keys = [hashlib.sha1(f'{model}\n{t}'.encode()).hexdigest() for t in texts]
    con = sqlite3.connect(f'file:{CACHE}?mode=ro', uri=True, timeout=120)
    found = {}
    try:
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            found.update({k: np.frombuffer(v, dtype=np.float32) for k, v in con.execute(
                f"SELECT key, v FROM vec WHERE key IN ({','.join('?' * len(chunk))})", chunk)})
    finally:
        con.close()
    if not found:
        return np.zeros((len(texts), 1)), np.zeros(len(texts), dtype=bool)
    X = np.zeros((len(texts), len(next(iter(found.values())))))
    have = np.zeros(len(texts), dtype=bool)
    for i, k in enumerate(keys):
        if k in found:
            X[i], have[i] = found[k], True
    return X, have


def words(texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """TF-IDF over words and word pairs, folded to 200 directions (enough for t-SNE's neighbours), unit length"""
    from sklearn.decomposition import TruncatedSVD
    from sklearn.feature_extraction.text import TfidfVectorizer
    T = TfidfVectorizer(stop_words='english', sublinear_tf=True, ngram_range=(1, 2), min_df=2).fit_transform(texts)
    have = np.asarray(T.multiply(T).sum(1)).ravel() > 0
    X = TruncatedSVD(min(200, T.shape[1] - 1), random_state=0).fit_transform(T)
    X /= np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-12)
    return X, have


def flatten(P: np.ndarray, three: bool = False) -> tuple[np.ndarray, np.ndarray | None]:
    """t-SNE of unit vectors (cosine) into 2 dimensions, and with `three` into 3 as well, each scaled to 0..1000. The 3-D
    one starts from the 2-D one (plus the next direction of the data for depth), so it keeps the flat map's
    arrangement and the page can lift the one into the other"""
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    Z = PCA(min(50, P.shape[1], P.shape[0] - 1), random_state=0).fit_transform(P)
    perplexity = min(30, max(5, len(P) // 4))
    Y = TSNE(2, metric='cosine', init='pca', perplexity=perplexity, random_state=0).fit_transform(Z)
    Y3 = None
    if three:
        start = np.column_stack([Y - Y.mean(0), (Z[:, 2] - Z[:, 2].mean()) * Y.std() / max(Z[:, 2].std(), 1e-9)])
        start = start / start[:, 0].std() * 1e-4  # t-SNE's own scale for a start
        Y3 = TSNE(3, metric='cosine', init=start, perplexity=perplexity, random_state=0).fit_transform(Z)

    def scaled(A):
        A = A - A.min(0)
        return A / max(float(A.max()), 1e-9) * 1000
    return scaled(Y), (scaled(Y3) if Y3 is not None else None)


def layout(entries: list[dict], spaces=tuple(SPACES), three: bool = False) -> dict:
    """entries: [{id, claims: [{text (as embedded), shown (as drawn), ok (confirmed)}], ...any fields to pass on}].
    Each motif's centre is the mean of its confirmed claims (all its claims when none is); with `three`, every place
    has a 3-D one too (xyz), grown from the flat one. Returns {spaces, motifs:
    [{...entry fields, xy: {space: [x, y]}, near: {space: [[motif index, likeness]]}, spread}], claims: [{t, xy, m:
    [[motif index, confirmed, likeness to that centre, itself left out]], k: key(text)}]}"""
    t0 = time.time()
    texts, at = [], {}
    for e in entries:
        for c in e['claims']:
            if c['text'] not in at:
                at[c['text']] = len(texts)
                texts.append(c['text'])
    shown = {at[c['text']]: c['shown'] for e in entries for c in e['claims']}
    members = [[(at[c['text']], bool(c.get('ok'))) for c in e['claims']] for e in entries]
    motifs = [{k: v for k, v in e.items() if k != 'claims'} for e in entries]
    claim_xy, claim_xyz = [{} for _ in texts], [{} for _ in texts]
    named = {}
    likeness = {}
    for space in spaces:
        model = SPACES[space]
        X, have = words(texts) if model is None else cached(model, texts)
        if not have.any():
            logger.warning("Motif space: no %s vectors in the cache", space)
            continue
        C, keep, sums, inside = [], [], {}, {}
        for i, mem in enumerate(members):
            use = [t for t, ok in mem if ok and have[t]] or [t for t, _ in mem if have[t]]
            if not use:
                continue
            s = X[use].sum(0)
            sums[i], inside[i] = s, set(use)
            C.append(s / max(np.linalg.norm(s), 1e-12))
            keep.append(i)
        if len(keep) < 5:
            continue
        C = np.array(C)
        ok = np.where(have)[0]
        Y, Y3 = flatten(np.vstack([X[ok], C]), three)
        for j, t in enumerate(ok):
            claim_xy[t][space] = [round(float(v), 1) for v in Y[j]]
            if Y3 is not None:
                claim_xyz[t][space] = [round(float(v), 1) for v in Y3[j]]
        S = C @ C.T
        np.fill_diagonal(S, -2)
        for j, i in enumerate(keep):
            motifs[i].setdefault('xy', {})[space] = [round(float(v), 1) for v in Y[len(ok) + j]]
            if Y3 is not None:
                motifs[i].setdefault('xyz', {})[space] = [round(float(v), 1) for v in Y3[len(ok) + j]]
            motifs[i].setdefault('near', {})[space] = [[keep[k], round(float(S[j, k]), 3)] for k in np.argsort(-S[j])[:NEAR]]
        if space == spaces[0]:  # how tight each motif is, in the first space: its claims' likeness to its centre
            for i in keep:
                for t, _ in members[i]:
                    if not have[t] or (t in inside[i] and len(inside[i]) == 1):
                        continue
                    s = sums[i] - X[t] if t in inside[i] else sums[i]  # a claim is left out of its own centre
                    likeness[t, i] = round(float(X[t] @ s / max(np.linalg.norm(s), 1e-12)), 3)
                vals = [likeness[t, i] for t, _ in members[i] if (t, i) in likeness]
                motifs[i]['spread'] = round(float(np.mean(vals)), 3) if vals else None
        named[space] = regions(motifs, keep, space)
        logger.info("Motif space: %s laid out, %d claims, %d centres (%.0f s)", space, len(ok), len(keep), time.time() - t0)
    of = [[] for _ in texts]
    for i, mem in enumerate(members):
        for t, ok_ in mem:
            of[t].append([i, int(ok_), likeness.get((t, i))])
    return {'spaces': [s for s in spaces if any(s in m.get('xy', {}) for m in motifs)], 'motifs': motifs, 'regions': named,
            'claims': [{'k': key(texts[t]), 't': shown[t], 'xy': claim_xy[t], 'm': of[t], **({'xyz': claim_xyz[t]} if claim_xyz[t] else {})}
                       for t in range(len(texts)) if claim_xy[t]]}


REGIONS = 15  # neighbourhoods the map is cut into for naming (fewer on a small index)
REGION_LEAST = 5  # a region's name needs this many of its motifs in the group
REGION_SHARE = 0.12  # and this share of them (groups are many and overlap: a region's leading one holds 15-25%)


def regions(motifs: list[dict], keep: list[int], space: str) -> list[dict]:
    """The map's neighbourhoods named like places (Oct 30, the person: "just the regions", not axes, which would mean
    nothing on a t-SNE map): the motifs cut into REGIONS by where they sit (k-means on the flat places), each named for
    the group most typical of it (its count times how much likelier the group is there than overall), no group used
    twice; a region with no clear group goes unnamed. Each name sits at the middle of its group's motifs there, flat and
    lifted: [{group (id), n, xy, xyz?}]"""
    from collections import Counter

    from sklearn.cluster import KMeans
    have = [i for i in keep if space in motifs[i].get('xy', {})]
    if len(have) < 20:
        return []
    P = np.array([motifs[i]['xy'][space] for i in have])
    k = max(4, min(REGIONS, len(have) // 60))
    cut = KMeans(k, n_init=10, random_state=0).fit_predict(P)
    total = Counter(g for i in have for g in motifs[i].get('groups', []))
    offers = []
    for r in range(k):
        inside = [have[j] for j in range(len(have)) if cut[j] == r]
        for g, n in Counter(g for i in inside for g in motifs[i].get('groups', [])).items():
            share = n / len(inside)
            if n >= REGION_LEAST and share >= REGION_SHARE:
                offers.append((n * share / (total[g] / len(have)), r, g, [i for i in inside if g in motifs[i].get('groups', [])]))
    out, named, used = [], set(), set()
    for _, r, g, members in sorted(offers, key=lambda o: -o[0]):
        if r in named or g in used:
            continue
        named.add(r)
        used.add(g)
        spot = {'group': g, 'n': len(members),
                'xy': [round(float(v), 1) for v in np.mean([motifs[i]['xy'][space] for i in members], 0)]}
        lifted = [motifs[i]['xyz'][space] for i in members if space in motifs[i].get('xyz', {})]
        if lifted:
            spot['xyz'] = [round(float(v), 1) for v in np.mean(lifted, 0)]
        out.append(spot)
    return out


def key(text: str) -> str:
    """A claim's key in a kept layout: the page joins it to the claim's text as shown today, so a claim the
    accusations screen holds later in the day leaves the page at the next build"""
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def today(entries: list[dict] | None = None, spaces=PUBLIC_SPACES, three: bool = True) -> dict | None:
    """The day's public layout: worked out from `entries` on the first call of the day (in the hourly build), then
    read back; None when there is none and no entries to make one. Its motifs carry their ids and its claims their
    keys, so each build joins them to the index and the screen as they stand then (and drops what's gone)"""
    try:
        with open(TODAY_FILE) as f:
            kept = json.load(f)
        fresh = kept.get('day') == date.today().isoformat() and kept.get('version') == VERSION
        if (fresh and (kept.get('three') or not three)) or entries is None:
            return kept
    except (OSError, ValueError):
        if entries is None:
            return None
    data = layout(entries, spaces, three)
    data['day'], data['three'], data['version'] = date.today().isoformat(), three, VERSION
    os.makedirs(os.path.dirname(TODAY_FILE), exist_ok=True)
    with open(TODAY_FILE + '.tmp', 'w') as f:
        json.dump(data, f, separators=(',', ':'))
    os.replace(TODAY_FILE + '.tmp', TODAY_FILE)
    return data


def spot(data: dict | None, space: str = PUBLIC_SPACES[0]) -> dict[str, list[float]]:
    """Each motif's place in a space, 0..1 each way: {motif id: [x, y]} (for the front page's cloud)"""
    if not data:
        return {}
    return {m['id']: [round(m['xy'][space][0] / 1000, 3), round(m['xy'][space][1] / 1000, 3)]
            for m in data['motifs'] if space in m.get('xy', {})}
