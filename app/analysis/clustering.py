import re
from collections import deque

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from app.analysis import local_models


# Function to form clusters
def form_clusters(cosine_sim, min_samples=10, threshold=0.5):
    print("Clustering with python.")
    # zero out diagonal
    np.fill_diagonal(cosine_sim, 0)
    # drop everything less than threshold
    cosine_sim[cosine_sim < threshold] = 0
    clusters = []
    while np.any(cosine_sim):
        # Start with the first available row
        first_index = np.where(np.any(cosine_sim, axis=1))[0][0]
        # Get all indices where similarity >= threshold
        involved_indices = np.where(cosine_sim[first_index] >= threshold)[0]
        # Add all connected components
        queue = deque(involved_indices)
        cluster = set(queue)
        while queue:
            current = queue.popleft()
            connected_indices = np.where(cosine_sim[current] >= threshold)[0]
            new_indices = set(connected_indices) - cluster
            queue.extend(new_indices)
            cluster.update(new_indices)
        # Mark these rows and columns as processed
        for idx in cluster:
            cosine_sim[idx, :] = 0
            cosine_sim[:, idx] = 0
        # Store the cluster
        if len(cluster) >= min_samples:
            clusters.append(cluster)
            print(f"Cluster len: {len(cluster)}, clusters formed: {len(clusters)}")
    return clusters


try:  # If the C extension is available, use it
    from app.analysis.maudlinlib import form_clusters as _c_form_clusters

    def form_clusters(cosine_sim, min_samples=10, threshold=0.5):
        # The C code reads the buffer as contiguous doubles with no checks, so anything else corrupts memory. A cluster
        # takes at least two headlines: below that the C code would return every unlinked row on its own, where the
        # Python version (which only visits linked rows) returns none
        return _c_form_clusters(np.ascontiguousarray(cosine_sim, dtype=np.float64), max(2, min_samples), threshold)
except ImportError:
    pass


def prepare_cosine(data):
    # TF-IDF Vectorizer
    vectorizer = TfidfVectorizer()
    tfidf_matrix = vectorizer.fit_transform(data)
    # Cosine Similarity
    cosine_sim = cosine_similarity(tfidf_matrix)
    return cosine_sim


# Dollar amounts in a headline ("$90", "$5,000", "$1.2 billion", "nearly $100"), for telling apart stories that
# read alike but are about different money: Trump's $90 Medicare checks vs. his $5,000 promise (#148)
MONEY = re.compile(r'\$\s?(\d[\d,]*(?:\.\d+)?)\s*(k|thousand|m|mn|million|b|bn|billion|t|trillion)?\b', re.IGNORECASE)
SCALE = {'k': 1e3, 'thousand': 1e3, 'm': 1e6, 'mn': 1e6, 'million': 1e6, 'b': 1e9, 'bn': 1e9, 'billion': 1e9,
         't': 1e12, 'trillion': 1e12}
MONEY_RATIO = 3  # amounts further apart than this are different money; closer is ordinary rounding ($90 ~ $100)


def money(title: str) -> list[float]:
    return [float(n.replace(',', '')) * SCALE.get((unit or '').lower(), 1) for n, unit in MONEY.findall(title)]


def unlink_money_conflicts(cosine_sim: np.ndarray, titles) -> np.ndarray:
    """Zero the similarity of headline pairs that both name dollar amounts and share none within MONEY_RATIO of each
    other, so similar wording about different sums doesn't chain two stories together. Headlines without amounts
    are left alone."""
    amounts = [money(t) for t in titles]
    for i, a in enumerate(amounts):
        if not a:
            continue
        for j in range(i + 1, len(amounts)):
            b = amounts[j]
            if b and not any(max(x, y) <= MONEY_RATIO * min(x, y) for x in a for y in b if min(x, y) > 0):
                cosine_sim[i, j] = cosine_sim[j, i] = 0
    return cosine_sim


# Rallies and campaign stops in different states (Oct 27 audit): feed templates like "Trump Participates in Midterm
# Rally in Mississippi" score 0.83-0.86 against the same line about Michigan or Texas, so one story held several
# rallies (17 of 43 headlines in the Mississippi story were Michigan's or Texas's). Not Washington: it's DC as often.
# On Oct 27's 2,945 story headlines it split a 98-headline cluster of five states' rallies
STATES = ['Alabama', 'Alaska', 'Arizona', 'Arkansas', 'California', 'Colorado', 'Connecticut', 'Delaware', 'Florida',
          'Georgia', 'Hawaii', 'Idaho', 'Illinois', 'Indiana', 'Iowa', 'Kansas', 'Kentucky', 'Louisiana', 'Maine',
          'Maryland', 'Massachusetts', 'Michigan', 'Minnesota', 'Mississippi', 'Missouri', 'Montana', 'Nebraska',
          'Nevada', 'New Hampshire', 'New Jersey', 'New Mexico', 'New York', 'North Carolina', 'North Dakota', 'Ohio',
          'Oklahoma', 'Oregon', 'Pennsylvania', 'Rhode Island', 'South Carolina', 'South Dakota', 'Tennessee', 'Texas',
          'Utah', 'Vermont', 'Virginia', 'West Virginia', 'Wisconsin', 'Wyoming']
STATE = re.compile(r'\b(' + '|'.join(sorted(STATES, key=len, reverse=True)) + r')\b')
VISIT = re.compile(r'\b(rall(y|ies|ying)|campaign(s|ing)? (in|stop)|stumps?|town hall|visits?|tour(s|ing)?)\b', re.I)


def places(title: str) -> set[str]:
    """The states a rally or campaign-stop headline names ('' for any other headline)"""
    return set(STATE.findall(title)) if VISIT.search(title) else set()


def unlink_place_conflicts(cosine_sim: np.ndarray, titles) -> np.ndarray:
    """Zero the similarity of two rally or campaign-stop headlines that name states and share none, so one tour's stops
    stay separate stories. Headlines naming no state are left alone"""
    where = [places(t) for t in titles]
    for i, a in enumerate(where):
        if not a:
            continue
        for j in range(i + 1, len(where)):
            if where[j] and not (a & where[j]):
                cosine_sim[i, j] = cosine_sim[j, i] = 0
    return cosine_sim


EMBEDDING_MODEL = 'minishlab/potion-base-8M'


def embed(texts: list[str]) -> np.ndarray:
    """Static sentence embeddings (model2vec). Matches headlines by meaning rather than shared words, so
    differently worded coverage of one story still clusters. Numpy only, a few ms per thousand headlines."""
    from app.analysis import embeddings
    return embeddings.static(texts, EMBEDDING_MODEL)


def prepare_embedding_cosine(texts):
    return cosine_similarity(embed(texts)).astype(np.float64)


# Stories use a bigger embedding model than the rest of the site: tested on Oct 4 2026 against model-judged headline
# pairs, mxbai-embed-large (through the local Ollama) made more coherent stories than potion-base-8M at the same
# coverage (methods log). Each model has its own similarity scale, so each has its own threshold; if Ollama can't
# embed, stories fall back to the static model at its threshold. Vectors are cached by headline text, so a run only
# embeds the headlines it hasn't seen (a few hundred an hour instead of the day's thousands).
STORY_MODEL = local_models.MXBAI
STORY_THRESHOLDS = {STORY_MODEL: 0.80, 'potion-base-8M': 0.70}  # the vectors and their cache: embeddings.py


def ollama_embed(texts: list[str], model: str = STORY_MODEL, cache: str = None, keep_days: float | None = None,
                 bulk: int | None = None) -> np.ndarray:
    """embeddings.ollama, the stories' cache by default"""
    from app.analysis import embeddings
    return embeddings.ollama(texts, model=model, cache_path=cache,
                             keep_days=embeddings.STORY_CACHE_DAYS if keep_days is None else keep_days,
                             bulk=embeddings.BULK if bulk is None else bulk)


def headline_vectors(texts) -> tuple[np.ndarray, str]:
    """(unit vectors for `texts`, the model that made them): mxbai through the local Ollama (cached), or the static
    model if Ollama can't embed. Callers keep a threshold per model, since each has its own similarity scale."""
    texts = list(texts)
    try:
        return ollama_embed(texts).astype(np.float64), STORY_MODEL
    except Exception as e:  # Ollama down, the model missing, a network refusal in tests
        import logging
        logging.getLogger(__name__).warning("Embeddings from %s failed (%s); using potion-base-8M", STORY_MODEL,
                                            type(e).__name__)
        v = embed(texts).astype(np.float64)
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9), 'potion-base-8M'


def story_similarity(texts) -> tuple[np.ndarray, float, str]:
    """(cosine similarity of the headlines, the story threshold for the model that made it, the model's name)."""
    texts = list(texts)
    try:
        v = ollama_embed(texts).astype(np.float64)
        return v @ v.T, STORY_THRESHOLDS[STORY_MODEL], STORY_MODEL
    except Exception as e:  # Ollama down, the model missing, a network refusal in tests: the static model instead
        import logging
        logging.getLogger(__name__).warning("Story embeddings from %s failed (%s); using potion-base-8M",
                                            STORY_MODEL, type(e).__name__)
        return prepare_embedding_cosine(texts), STORY_THRESHOLDS['potion-base-8M'], 'potion-base-8M'


# The second pass (the person's idea, Oct 11; Atropos tested it): stories are formed by meaning (embeddings), then each
# story's headlines are compared by their words (TF-IDF, fitted on the story's own headlines) and cut where they fall
# into two groups that barely share words: a spectral bisection, the normalized cut. On 345 cuts of a week's stories,
# judged by Gemma under two wordings, cuts scoring under 0.6 were two events 18 of 18 times (0.6-0.7: 69%; over 0.8:
# almost never). Each side must be a story itself (SEAM_OUTLETS outlets); a side is cut again, SEAM_DEPTH deep.
SEAM = 0.6
SEAM_DEPTH = 3
# A cut is made only when Gemma, asked both ways, says the sides are two events (Oct 12: on the last day's stories the
# score alone cut 9, three of them one event, at the same scores as the right ones; Atropos's 18 of 18 were cuts the
# judge had confirmed). The sides shown are each side's SEAM_SHOWN most central headlines; answers cached in SEAM_CACHE.
SEAM_SHOWN = 6
SEAM_MODEL = local_models.BIG
SEAM_ASK = ["""Two groups of news headlines, from one story on a news site:

Group A:
{a}

Group B:
{b}

Do the two groups report one news event (the same announcement, incident, decision, ruling, report or game, perhaps
with more details or reactions), or two different events (a separate incident, another person's action, a later
development such as a new statement, a response, a vote or an arrest)? Go by what most headlines in each group report.

reason: one sentence
one_event: true or false""", """Group A:
{a}

Group B:
{b}

A news editor has these headlines on one story card. Should they stay on one card, because both groups report one
event, or be two cards, because the groups report different events, even if one led to the other?

reason: one sentence
one_event: true if one card"""]
SEAM_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 400},
                                                "one_event": {"type": "boolean"}}, "required": ["reason", "one_event"]}


def two_events(a: list[str], b: list[str], cache: dict) -> bool:
    """Gemma, asked both ways, says the two groups of headlines are two events; False when unsure or unasked"""
    import hashlib
    import json
    from app.analysis import llm
    key = hashlib.sha1(json.dumps([a, b]).encode()).hexdigest()
    if key not in cache:
        shown = {'a': '\n'.join(f'- {t}' for t in a), 'b': '\n'.join(f'- {t}' for t in b)}
        answers = [llm.complete_json(q.format(**shown), SEAM_SCHEMA, max_tokens=300, model=SEAM_MODEL) for q in SEAM_ASK]
        if any(x is None for x in answers):
            return False  # not cached: asked again next run
        cache[key] = [bool(x['one_event']) for x in answers] + [answers[0].get('reason', ''), a, b]  # sides: for the
        # experiments page's list of the cuts production weighed
    return not cache[key][0] and not cache[key][1]


def central(idx: list[int], W: np.ndarray, titles: list[str], n: int = SEAM_SHOWN) -> list[str]:
    """A side's most central headlines (most alike the rest of it), each once"""
    out = []
    for k in np.argsort(-W[np.ix_(idx, idx)].sum(1)):
        t = ' '.join(titles[idx[k]].split())
        if t not in out:
            out.append(t)
        if len(out) == n:
            break
    return out


def best_cut(W: np.ndarray, outlets: list, min_outlets: int) -> tuple[float, np.ndarray] | None:
    """(normalized cut, the mask of one side) for the cleanest cut of the likeness matrix W whose sides each have
    min_outlets outlets, or None"""
    W = W.copy()
    np.fill_diagonal(W, 0)
    d = W.sum(1) + 1e-9
    L = np.eye(len(W)) - W / np.sqrt(np.outer(d, d))
    _, vecs = np.linalg.eigh(L)
    f = vecs[:, 1] / np.sqrt(d)
    best = None
    for cut in np.unique(np.quantile(f, np.linspace(0.05, 0.95, 37))):
        A = f <= cut
        if len({outlets[i] for i in np.flatnonzero(A)}) < min_outlets or \
                len({outlets[i] for i in np.flatnonzero(~A)}) < min_outlets:
            continue
        c = W[np.ix_(A, ~A)].sum()
        ncut = c / (W[A].sum() + 1e-9) + c / (W[~A].sum() + 1e-9)
        if best is None or ncut < best[0]:
            best = (float(ncut), A)
    return best


def split_seams(clusters: list, texts: list[str], outlets: list, min_outlets: int,
                titles: list[str] | None = None, confirm=None, roots: list | None = None) -> tuple[list, list[dict]]:
    """The clusters with each cut where its headlines' words (texts: the processed headlines, as Atropos tested) fall
    apart (a cut scoring under SEAM, and confirmed by `confirm(side a's titles, side b's)` if given); and the cuts made,
    each {'ncut', 'sizes', 'a', 'b'} (each side's most central titles). `roots`, if given, is filled with each returned
    cluster's place in `clusters`: the sides of one cut share it, so a later step doesn't join what the cut parted"""
    titles = titles or texts
    out, made = [], []
    todo = [(sorted(c), 0, r) for r, c in enumerate(clusters)]
    while todo:
        idx, depth, root = todo.pop()
        if depth < SEAM_DEPTH and len({outlets[i] for i in idx}) >= 2 * min_outlets:
            try:
                T = TfidfVectorizer().fit_transform([texts[i] for i in idx])
                W = (T @ T.T).toarray()
                b = best_cut(W, [outlets[i] for i in idx], min_outlets)
            except ValueError:  # no words left after the vectorizer's own cleaning
                b = None
            if b and b[0] < SEAM:
                a_k, b_k = list(np.flatnonzero(b[1])), list(np.flatnonzero(~b[1]))
                sides = central(a_k, W, [titles[i] for i in idx]), central(b_k, W, [titles[i] for i in idx])
                if confirm is None or confirm(*sides):
                    a_idx, b_idx = [idx[k] for k in a_k], [idx[k] for k in b_k]
                    made.append({'ncut': round(b[0], 3), 'sizes': [len(a_idx), len(b_idx)], 'a': sides[0], 'b': sides[1]})
                    todo += [(a_idx, depth + 1, root), (b_idx, depth + 1, root)]
                    continue
        out.append(set(idx))
        if roots is not None:
            roots.append(root)
    return out, made


def label_clusters(data, clusters):
    cluster_labels = [-1] * len(data)
    for cluster_id, cluster_indices in enumerate(clusters):
        for idx in cluster_indices:
            cluster_labels[idx] = cluster_id
    data['cluster'] = cluster_labels
    return data
