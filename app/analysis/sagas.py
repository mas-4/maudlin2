"""Sagas: one ongoing story told in several parts. Stories are tight clusters of headlines about one development
("Hochul hands the Cornell case to the AG", "Trump says James won't be fair"); a saga groups the developments of the
same running story so the front page can count and show them together.

Two stories join when their centers (mean headline embeddings) are close and they share a distinctive word: one that's
common in both stories' headlines but rare across the day's headlines ("Cornell", "Ukraine"). Merging is greedy, highest
similarity first, re-centering after every merge, so a saga can't grow by a chain of one-off links. Headlines that
didn't make any story but clearly belong (close to the saga's center and carrying its word) count toward its reach.

Sagas are kept across days (link_sagas): each run compares today's stories with the last SAGA_MEMORY of saved
stories, starting from the sagas already saved, so a saga grows (or merges into another) but never loses a part when
its older parts leave the front pages: a story told in four parts stays four parts."""
import re
from collections import Counter
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytz

from app.analysis import llm
from app.analysis.clustering import embed
from app.models import Session, SqlLock, Saga, Story, StoryHeadline, Headline, Article, Agency
from app.utils import get_logger

logger = get_logger(__name__)

SAGA_SIMILARITY = 0.58  # story centers this close may be one saga; unrelated stories sit below ~0.56
NAME_MIN_SHARE = 0.3  # a distinctive word appears in at least this share of each side's headlines...
NAME_MAX_SHARE = 0.04  # ...and in no more than this share of all the day's headlines
RELATED_SIMILARITY = 0.6  # an unclustered headline this close to a saga's center (with its word) counts toward it
SAGA_MEMORY = td(days=7)  # saved stories this recent can join today's stories in a saga
RENAME_GROWTH = 2  # a saga is renamed when it has grown to this many times the parts it was named with

WORD = re.compile(r"[A-Za-z][A-Za-z']{3,}")  # hyphens split words: "UK-Iranian" carries "Iranian"

NAME_PROMPT = """These headlines are parts of one ongoing news story. Name the story in 2 to 6 words, the way a \
newspaper would label a running story (for example "Cornell fraternity rape case" or "Russia-Ukraine peace talks"). \
Plain words, no quotes, no dates.

{headlines}"""
NAME_SCHEMA = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
_names: dict[frozenset, str] = {}


def words(title: str) -> set[str]:
    return {w.lower().strip("'-") for w in WORD.findall(title)}


def proper_nouns(titles: list[str]) -> set[str]:
    """Words outlets capitalize mid-sentence (names: Cornell, James, Iranian), from sentence-case headlines only:
    Title Case headlines capitalize everything, so they say nothing about which words are names."""
    seen, capital = Counter(), Counter()
    for title in titles:
        found = WORD.findall(title)
        if found and sum(w[0].isupper() for w in found) / len(found) > 0.6:
            continue
        for i, word in enumerate(re.findall(r"[A-Za-z][A-Za-z']*", title)):
            if i == 0 or len(word) < 4:
                continue
            seen[word.lower()] += 1
            capital[word.lower()] += word[0].isupper()
    return {w for w, n in seen.items() if capital[w] >= 0.6 * n}


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


def _merge(groups: dict, vectors: np.ndarray, bags: list[set], frequency: Counter, common: float,
           names_ok: set[str]) -> dict:
    """Greedy saga merging (as in find_sagas) over `groups`: key -> {'members': [...], 'rows': [title rows]}. Two
    groups join only if they share a distinctive word that's a name (`names_ok`): sagas are kept for good, so a
    shared common noun ("rally") isn't enough to tie two stories together forever."""
    def center(rows):
        v = vectors[rows].mean(axis=0)
        return v / np.linalg.norm(v)

    def distinctive(rows):
        counts = Counter(w for r in rows for w in bags[r])
        return {w for w, n in counts.items() if n >= NAME_MIN_SHARE * len(rows) and frequency[w] <= common}

    centers = {k: center(g['rows']) for k, g in groups.items()}
    names = {k: distinctive(g['rows']) for k, g in groups.items()}
    while True:
        keys = list(groups)
        if len(keys) < 2:
            break
        matrix = np.array([centers[k] for k in keys])
        similarity = matrix @ matrix.T
        np.fill_diagonal(similarity, -1)
        best = None
        for i, j in zip(*np.where(np.triu(similarity, 1) >= SAGA_SIMILARITY)):
            a, b = keys[i], keys[j]
            if names[a] & names[b] & names_ok and (best is None or similarity[i, j] > best[0]):
                best = (similarity[i, j], a, b)
        if best is None:
            break
        _, a, b = best
        groups[a]['members'] += groups[b]['members']
        groups[a]['rows'] += groups[b]['rows']
        del groups[b], centers[b], names[b]
        centers[a], names[a] = center(groups[a]['rows']), distinctive(groups[a]['rows'])
    for k in groups:
        groups[k]['words'] = names[k]
        groups[k]['center'] = centers[k]
    return groups


def _past_stories(exclude: set[int], since: dt) -> dict[int, dict]:
    """Saved stories seen since `since` that aren't in today's clusters: their saga, headline titles and outlets."""
    with Session() as s:
        rows = s.query(Story.id, Story.saga_id, Headline.title, Agency.name).join(
            StoryHeadline, StoryHeadline.story_id == Story.id).join(Headline, Headline.id == StoryHeadline.headline_id) \
            .join(Article, Article.id == Headline.article_id).join(Agency, Agency.id == Article.agency_id) \
            .filter(Story.last_seen >= since).all()
    past = {}
    for story_id, saga_id, title, agency in rows:
        if story_id in exclude:
            continue
        entry = past.setdefault(story_id, {'saga': saga_id, 'titles': [], 'outlets': set()})
        entry['titles'].append(title.strip())
        entry['outlets'].add(agency)
    return past


def link_sagas(headlines: pd.DataFrame, stories: pd.DataFrame, story_of: dict[int, int]) -> dict[int, dict]:
    """Sagas kept across days. `headlines` and `stories` as for find_sagas; `story_of`: cluster -> saved story id.
    Today's stories and the last SAGA_MEMORY of saved stories are merged, starting from the sagas already saved;
    every group of two or more stories with a part on the front pages now is saved as (or added to) a saga. Returns
    the active sagas keyed by -saga id (so they never collide with cluster ids): today's clusters in it, every part
    (earlier ones included), its name, words and outlets."""
    if stories.empty:
        return {}
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    current = {int(k): story_of[int(k)] for k in stories['cluster'].unique() if int(k) in story_of}
    past = _past_stories(set(current.values()), now - SAGA_MEMORY)
    with Session() as s:
        saga_of = {sid: saga for sid, saga in s.query(Story.id, Story.saga_id).filter(
            Story.id.in_(list(current.values())), Story.saga_id.isnot(None))}
    saga_of.update({sid: p['saga'] for sid, p in past.items() if p['saga'] is not None})

    # One list of titles: today's considered headlines, then each past story's headlines
    titles = headlines['title'].tolist()
    rows_of = {('now', k): list(headlines.index[headlines['cluster'] == k]) for k in current}
    for sid, p in past.items():
        rows_of[('past', sid)] = list(range(len(titles), len(titles) + len(p['titles'])))
        titles += p['titles']
    vectors = embed(titles)
    vectors = vectors / np.linalg.norm(vectors, axis=1, keepdims=True)
    bags = [words(t) for t in titles]
    frequency = Counter(w for bag in bags for w in bag)
    common = NAME_MAX_SHARE * len(headlines)

    # Start from the saved sagas: their parts begin as one group, so a saga can't come apart
    groups = {}
    for member, rows in rows_of.items():
        story_id = current[member[1]] if member[0] == 'now' else member[1]
        key = ('saga', saga_of[story_id]) if story_id in saga_of else member
        group = groups.setdefault(key, {'members': [], 'rows': []})
        group['members'].append(member)
        group['rows'] += rows
    groups = _merge(groups, vectors, bags, frequency, common, proper_nouns(titles))

    active = {}
    unclustered = headlines.index[headlines['cluster'] == -1]
    with Session() as s, SqlLock:
        for group in groups.values():
            members = group['members']
            now_clusters = [m[1] for m in members if m[0] == 'now']
            if len(members) < 2 or not now_clusters:
                continue
            story_ids = [current[k] for k in now_clusters] + [m[1] for m in members if m[0] == 'past']
            known = sorted({saga_of[i] for i in story_ids if i in saga_of})
            if known:
                saga = s.get(Saga, known[0])  # the oldest keeps its id; any other saga merges into it
                for absorbed in known[1:]:
                    s.query(Story).filter(Story.saga_id == absorbed).update({'saga_id': saga.id})
                    s.query(Saga).filter(Saga.id == absorbed).delete()
            else:
                saga = Saga(first_seen=now, last_seen=now)
                s.add(saga)
                s.flush()
            s.query(Story).filter(Story.id.in_(story_ids)).update({'saga_id': saga.id})
            saga.last_seen = now
            saga.words = ','.join(sorted(group['words']))[:255]
            parts = s.query(Story).filter(Story.saga_id == saga.id).order_by(Story.first_seen).all()
            if not saga.name or len(parts) >= RENAME_GROWTH * (saga.named_with or 1):
                saga.name = name(stories, now_clusters)
                saga.named_with = len(parts)
            # Every outlet on any part, plus related headlines today that made no story
            outlets = set(stories[stories['cluster'].isin(now_clusters)]['agency'])
            for p in parts:
                if p.id in past:
                    outlets |= past[p.id]['outlets']
            related = [r for r in unclustered
                       if float(vectors[r] @ group['center']) >= RELATED_SIMILARITY and bags[r] & group['words']]
            outlets |= set(headlines.loc[related, 'agency'])
            cluster_of = {v: k for k, v in current.items()}
            active[-saga.id] = {
                'id': saga.id, 'name': saga.name, 'words': sorted(group['words']), 'outlets': len(outlets),
                'related': len(related), 'clusters': now_clusters, 'size': len(parts),
                'parts_all': [{'story': p.id, 'cluster': cluster_of.get(p.id), 'label': p.label,
                               'first_seen': p.first_seen, 'last_seen': p.last_seen,
                               'outlets': len(past[p.id]['outlets']) if p.id in past else None} for p in parts],
            }
        s.commit()
    logger.info("%i active sagas: %s", len(active),
                '; '.join(f"{a['name']} ({a['size']} parts, {len(a['clusters'])} on front pages, {a['outlets']} outlets)"
                          for a in active.values()))
    return active
