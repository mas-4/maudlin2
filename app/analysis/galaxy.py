"""The headline galaxy (Nov 5, the person: "a huge cluster map of all headlines ever"): every headline we have read,
placed on a flat map so headlines that say similar things sit close together. Drawn on the news over time page
(app/site/page_over_time.py, static/over_time.js).

Each headline is embedded with the site's static model (clustering.embed: model2vec, CPU, a few seconds for all of
them), folded to DIMS directions by PCA. A sample of LANDMARKS headlines is laid out by t-SNE (about 30 s); every
other headline sits at the likeness-weighted middle of its NEIGHBOURS nearest landmarks. TOPICS rough topics come from
k-means on the same vectors, each named by its most telling words.

The layout is kept in the cache (LAYOUT_FILE). Each build only places the headlines that are new since (a second or
two); once RELAYOUT_DAYS have passed the landmarks are drawn again and laid out afresh, starting from where they sat,
so the map keeps its shape from week to week.

    today(ids, titles)   the layout for these headlines: {ids, xy (0..1), topic, names, made}"""
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import numpy as np

from app.utils import Config, get_logger

logger = get_logger(__name__)

FOLDER = os.path.join(Config.cache, 'galaxy')
LAYOUT_FILE = os.path.join(FOLDER, 'layout.npz')
VERSION = 1  # of the kept layout: a new one is laid out afresh
LANDMARKS = 20000
RELAYOUT_DAYS = 7
NEIGHBOURS = 8
SHARPNESS = 20  # how much more a nearer landmark counts: weights are exp(SHARPNESS x likeness)
DIMS = 50
TOPICS = 8
JITTER = 0.002  # a placed headline is nudged this far at most, so ones with the same neighbours don't stack
CHUNK = 10000


def embed(texts: list[str]) -> np.ndarray:
    from app.analysis import clustering
    return clustering.embed(texts)


def unit(X) -> np.ndarray:
    X = np.asarray(X, dtype=np.float32)
    return X / np.maximum(np.linalg.norm(X, axis=1, keepdims=True), 1e-9)


def project(X: np.ndarray, mean: np.ndarray, comps: np.ndarray) -> np.ndarray:
    """Unit vectors in the kept PCA directions"""
    return unit((unit(X) - mean) @ comps.T)


def nearest(Z: np.ndarray, ZL: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    """For each row of Z, its k most alike rows of ZL (unit vectors) and their likeness; in chunks, on threads (numpy
    lets go of the lock while it multiplies and partitions)"""
    k = min(k, len(ZL))

    def part(i):
        S = Z[i:i + CHUNK] @ ZL.T
        idx = np.argpartition(-S, k - 1, axis=1)[:, :k] if k < len(ZL) else np.tile(np.arange(len(ZL)), (len(S), 1))
        return idx, np.take_along_axis(S, idx, 1)
    with ThreadPoolExecutor(min(8, os.cpu_count() or 1)) as pool:
        parts = list(pool.map(part, range(0, len(Z), CHUNK)))
    if not parts:
        return np.zeros((0, k), dtype=int), np.zeros((0, k), dtype=np.float32)
    return np.vstack([p[0] for p in parts]), np.vstack([p[1] for p in parts])


def jitter(ids: np.ndarray) -> np.ndarray:
    """A small nudge each way, the same for a headline every time (from its id)"""
    h = (np.asarray(ids, dtype=np.uint64) * np.uint64(2654435761)) % np.uint64(1 << 32)
    a = (h % np.uint64(1000)).astype(np.float32) / 1000 - 0.5
    b = ((h // np.uint64(1000)) % np.uint64(1000)).astype(np.float32) / 1000 - 0.5
    return np.column_stack([a, b]) * 2 * JITTER


def place(Z: np.ndarray, ZL: np.ndarray, lxy: np.ndarray, ids: np.ndarray, k: int = NEIGHBOURS) -> np.ndarray:
    """Places for headlines (unit vectors Z): the likeness-weighted middle of their k nearest landmarks' places"""
    if not len(Z):
        return np.zeros((0, 2), dtype=np.float32)
    idx, s = nearest(Z, ZL, k)
    w = np.exp((s - s.max(1, keepdims=True)) * SHARPNESS)
    xy = (lxy[idx] * w[..., None]).sum(1) / w.sum(1, keepdims=True)
    return np.clip(xy + jitter(ids), 0, 1).astype(np.float32)


def flatten(Z: np.ndarray, init: np.ndarray | None = None) -> np.ndarray:
    """t-SNE of the landmarks into two dimensions, scaled to 0..1 (the few strays past the 0.05th and 99.95th
    percentiles held at the edge); `init`: where they sat last time, so the map keeps its shape"""
    from sklearn.manifold import TSNE
    if init is not None:
        start = init - init.mean(0)
        start = start / max(float(start[:, 0].std()), 1e-9) * 1e-4  # t-SNE's own scale for a start
    else:
        start = 'pca'
    perplexity = min(30, max(5, (len(Z) - 1) // 3))
    Y = TSNE(2, init=start, perplexity=perplexity, random_state=0, n_jobs=-1, metric='cosine').fit_transform(Z)
    lo, hi = np.percentile(Y, 0.05, axis=0), np.percentile(Y, 99.95, axis=0)
    span = max(float((hi - lo).max()), 1e-9)
    Y = (Y - lo) / span + (1 - (hi - lo) / span) / 2  # the long side fills 0..1, the short one centred
    return np.clip(Y, 0, 1).astype(np.float32)


GENERIC = 3  # a word must be this many times likelier in a topic than overall to name it (less with few topics)


def topic_names(titles: list[str], topic: np.ndarray, k: int, words: int = 3) -> list[str]:
    """Each topic's most telling words: common in its headlines and much likelier there than in the rest (each word's
    share in the topic times how many times likelier it is there), so words every headline uses ("says", "new")
    name none"""
    from sklearn.feature_extraction.text import CountVectorizer
    import scipy.sparse as sp
    try:
        cv = CountVectorizer(stop_words='english', min_df=min(20, max(1, len(titles) // 1000)), binary=True,
                             token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z'-]+\b")
        C = cv.fit_transform(titles)
    except ValueError:  # no words at all
        return [''] * k
    M = np.asarray((sp.csr_matrix((np.ones(len(topic)), (topic, np.arange(len(topic)))), shape=(k, len(topic))) @ C).todense())
    vocab = cv.get_feature_names_out()
    sizes = np.bincount(topic, minlength=k).astype(float)
    overall = M.sum(0) / max(len(topic), 1)
    out = []
    for t in range(k):
        share = M[t] / max(sizes[t], 1)
        lift = share / np.maximum(overall, 1e-9)
        score = np.where(lift >= min(GENERIC, 0.75 * k), share * np.log(np.maximum(lift, 1)), 0)
        best = [vocab[i] for i in np.argsort(-score)[:words] if score[i] > 0]
        out.append(' · '.join(best))
    return out


def fresh(ids: np.ndarray, titles: list[str], X: np.ndarray, kept: dict | None) -> dict:
    """A new layout: PCA and topics fitted on a sample of landmarks, the landmarks laid out by t-SNE (from their kept
    places, if any), everyone else placed around them"""
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
    t0 = time.time()
    rng = np.random.default_rng(0)
    L = np.sort(rng.choice(len(ids), min(LANDMARKS, len(ids)), replace=False))
    U = unit(X)
    pca = PCA(min(DIMS, len(L) - 1, U.shape[1]), random_state=0).fit(U[L])
    mean, comps = pca.mean_.astype(np.float32), pca.components_.astype(np.float32)
    Z = unit((U - mean) @ comps.T)
    init = None
    if kept is not None:
        at = {int(i): n for n, i in enumerate(kept['ids'])}
        if all(int(i) in at for i in ids[L]):
            init = kept['xy'][[at[int(i)] for i in ids[L]]]
    lxy = flatten(Z[L], init)
    xy = place(Z, Z[L], lxy, ids)
    xy[L] = lxy
    k = min(TOPICS, len(L))
    km = KMeans(k, n_init=4, random_state=0).fit(Z[L])
    topic = km.predict(Z)
    order = np.argsort(-np.bincount(topic, minlength=k), kind='stable')  # the biggest topic first, so it keeps its color
    rank = np.empty(k, dtype=int)
    rank[order] = np.arange(k)
    topic = rank[topic].astype(np.uint8)
    centres = km.cluster_centers_[order].astype(np.float32)
    names = topic_names(titles, topic, k)
    logger.info("Galaxy: laid out %d headlines around %d landmarks (%.0f s)", len(ids), len(L), time.time() - t0)
    return {'ids': ids.astype(np.int64), 'xy': xy, 'topic': topic, 'landmarks': ids[L].astype(np.int64),
            'mean': mean, 'comps': comps, 'centres': centres, 'names': np.array(names), 'made': date.today().isoformat(),
            'version': VERSION}


def update(ids: np.ndarray, titles: list[str], kept: dict) -> dict:
    """The kept layout for today's headlines: those gone dropped, new ones placed around the kept landmarks and given
    the nearest topic"""
    at = {int(i): n for n, i in enumerate(kept['ids'])}
    have = np.array([int(i) in at for i in ids], dtype=bool)
    rows = np.array([at.get(int(i), 0) for i in ids], dtype=int)
    xy = kept['xy'][rows].copy() if len(ids) else np.zeros((0, 2), dtype=np.float32)
    topic = kept['topic'][rows].copy() if len(ids) else np.zeros(0, dtype=np.uint8)
    new = np.where(~have)[0]
    pos = {int(i): n for n, i in enumerate(ids)}
    landmarks = np.array([i for i in kept['landmarks'] if int(i) in pos], dtype=np.int64)
    if len(new) and not len(landmarks):
        return fresh(ids, titles, embed(titles), None)
    if len(new):
        lrow = np.array([pos[int(i)] for i in landmarks])
        Z = project(embed([titles[n] for n in new]), kept['mean'], kept['comps'])
        ZL = project(embed([titles[n] for n in lrow]), kept['mean'], kept['comps'])
        xy[new] = place(Z, ZL, xy[lrow], ids[new])
        topic[new] = np.argmax(Z @ kept['centres'].T, axis=1).astype(np.uint8)
    return {**kept, 'ids': ids.astype(np.int64), 'xy': xy, 'topic': topic, 'landmarks': landmarks, 'placed': len(new)}


def load() -> dict | None:
    try:
        with np.load(LAYOUT_FILE, allow_pickle=False) as f:
            kept = {k: f[k] for k in f.files}
    except (OSError, ValueError, KeyError):
        return None
    kept['made'], kept['version'] = str(kept['made']), int(kept['version'])
    return kept


def save(layout: dict):
    os.makedirs(FOLDER, exist_ok=True)
    keep = {k: layout[k] for k in ('ids', 'xy', 'topic', 'landmarks', 'mean', 'comps', 'centres', 'names', 'made',
                                   'version')}
    with open(LAYOUT_FILE + '.tmp', 'wb') as f:
        np.savez(f, **keep)
    os.replace(LAYOUT_FILE + '.tmp', LAYOUT_FILE)


def stale(kept: dict | None, today: date | None = None) -> bool:
    if kept is None or kept.get('version') != VERSION:
        return True
    try:
        made = date.fromisoformat(kept['made'])
    except ValueError:
        return True
    return ((today or date.today()) - made).days >= RELAYOUT_DAYS


def today(ids, titles: list[str]) -> dict:
    """The layout for every headline (ids in the order the page draws them): kept and added to, or laid out afresh
    once a week. Returns {ids, xy (float32, 0..1), topic (uint8), names (each topic's words), made (ISO day)}"""
    ids = np.asarray(ids, dtype=np.int64)
    kept = load()
    if len(ids) < 10:
        return {'ids': ids, 'xy': np.zeros((len(ids), 2), dtype=np.float32), 'topic': np.zeros(len(ids), dtype=np.uint8),
                'names': np.array([]), 'made': date.today().isoformat()}
    t0 = time.time()
    if kept is not None and kept.get('version') == VERSION:
        out = update(ids, titles, kept)  # first, so a relayout starts from everyone's place
        if stale(kept):
            out = fresh(ids, titles, embed(titles), out)
    else:
        out = fresh(ids, titles, embed(titles), None)
    save(out)
    logger.info("Galaxy: %d headlines, %d newly placed, layout of %s (%.1f s)", len(ids), out.get('placed', len(ids)),
                out['made'], time.time() - t0)
    return out
