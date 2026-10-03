"""Sagas: one ongoing story told in several parts. Stories are tight clusters of headlines about one development
("Hochul hands the Cornell case to the AG", "Trump says James won't be fair"); a saga groups the developments of the
same running story so the front page can count and show them together.

Two stories join when their centers (mean headline embeddings) are close and they share a distinctive word: one that's
common in both stories' headlines but rare across the day's headlines ("Cornell", "Ukraine"). Merging is greedy, highest
similarity first, re-centering after every merge, so a saga can't grow by a chain of one-off links. Headlines that
didn't make any story but clearly belong (close to the saga's center and carrying its word) count toward its reach."""
import re
from collections import Counter

import numpy as np
import pandas as pd

from app.analysis import llm
from app.analysis.clustering import embed
from app.utils import get_logger

logger = get_logger(__name__)

SAGA_SIMILARITY = 0.58  # story centers this close may be one saga; unrelated stories sit below ~0.56
NAME_MIN_SHARE = 0.3  # a distinctive word appears in at least this share of each side's headlines...
NAME_MAX_SHARE = 0.04  # ...and in no more than this share of all the day's headlines
RELATED_SIMILARITY = 0.6  # an unclustered headline this close to a saga's center (with its word) counts toward it

WORD = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")

NAME_PROMPT = """These headlines are parts of one ongoing news story. Name the story in 2 to 6 words, the way a \
newspaper would label a running story (for example "Cornell fraternity rape case" or "Russia-Ukraine peace talks"). \
Plain words, no quotes, no dates.

{headlines}"""
NAME_SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
_names: dict[frozenset, str] = {}


def words(title: str) -> set[str]:
    return {w.lower().strip("'-") for w in WORD.findall(title)}


def find_sagas(headlines: pd.DataFrame, stories: pd.DataFrame) -> dict[int, dict]:
    """`headlines`: every headline considered for stories, positionally indexed, with 'title', 'agency' and 'cluster'
    (-1 for none). `stories`: the headlines kept in stories, with 'cluster' and 'agency'. Returns each saga of two or
    more stories, keyed by an id: its member clusters, a name, its distinctive words and its outlets."""
    if stories.empty:
        return {}
    titles = headlines['title'].tolist()
    vectors = embed(titles)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    bags = [words(t) for t in titles]
    frequency = Counter(w for bag in bags for w in bag)
    common = NAME_MAX_SHARE * len(titles)

    def center(rows):
        v = vectors[rows].mean(axis=0)
        return v / np.linalg.norm(v)

    def distinctive(rows):
        counts = Counter(w for r in rows for w in bags[r])
        return {w for w, n in counts.items() if n >= NAME_MIN_SHARE * len(rows) and frequency[w] <= common}

    groups = {int(k): {'clusters': [int(k)], 'rows': list(headlines.index[headlines['cluster'] == k])}
              for k in sorted(stories['cluster'].unique())}
    while True:
        keys = list(groups)
        centers = {k: center(groups[k]['rows']) for k in keys}
        names = {k: distinctive(groups[k]['rows']) for k in keys}
        best = None
        for i, a in enumerate(keys):
            for b in keys[i + 1:]:
                similarity = float(centers[a] @ centers[b])
                if similarity >= SAGA_SIMILARITY and names[a] & names[b] and (best is None or similarity > best[0]):
                    best = (similarity, a, b)
        if best is None:
            break
        _, a, b = best
        groups[a]['clusters'] += groups[b]['clusters']
        groups[a]['rows'] += groups[b]['rows']
        del groups[b]

    sagas = {}
    unclustered = headlines.index[headlines['cluster'] == -1]
    for key, group in groups.items():
        if len(group['clusters']) < 2:
            continue
        mid, marks = center(group['rows']), distinctive(group['rows'])
        related = [r for r in unclustered if float(vectors[r] @ mid) >= RELATED_SIMILARITY and bags[r] & marks]
        outlets = set(stories[stories['cluster'].isin(group['clusters'])]['agency']) | set(headlines.loc[related, 'agency'])
        sagas[key] = {'clusters': group['clusters'], 'words': sorted(marks), 'outlets': len(outlets),
                      'related': len(related), 'name': name(stories, group['clusters'])}
    logger.info("%i sagas from %i stories: %s", len(sagas), len(groups) + sum(len(s['clusters']) - 1 for s in sagas.values()),
                '; '.join(f"{s['name']} ({len(s['clusters'])} stories, {s['outlets']} outlets)" for s in sagas.values()))
    return sagas


def name(stories: pd.DataFrame, clusters: list[int]) -> str:
    """A short name for the saga from the language model, or its biggest story's first headline without one."""
    sample = []
    for k in clusters:
        sample += stories[stories['cluster'] == k]['title'].head(3).tolist()
    key = frozenset(sample)
    if key not in _names:
        answer = llm.complete_json(NAME_PROMPT.format(headlines='\n'.join(f'- {t}' for t in sample)), NAME_SCHEMA,
                                   max_tokens=32)
        label = (answer or {}).get('name', '').strip().strip('"')
        if not label:
            biggest = max(clusters, key=lambda k: (stories['cluster'] == k).sum())
            label = stories[stories['cluster'] == biggest]['title'].iloc[0]
        _names[key] = label[:80]
    return _names[key]
