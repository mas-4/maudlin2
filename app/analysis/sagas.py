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
import hashlib
import json
import os
import re
from collections import Counter
from typing import Optional
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytz

from app.analysis import llm
from app.analysis.clustering import embed
from app.models import Session, SqlLock, Saga, Story, StoryHeadline, Headline, Article, Agency
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

# Story centers this close (potion-base-8M) may be one saga; the shared-name rule and the 30B judge decide. Oct 5, on 118
# story pairs sharing a name: 0.58 let 6 of the 8 running stories through to the judge, 0.54 all 8 (3 more questions);
# mxbai separated them no better (methods log)
SAGA_SIMILARITY = 0.54
NAME_MIN_SHARE = 0.3  # a distinctive word appears in at least this share of one side's headlines...
NAME_MIN_OTHER = 0.1  # ...and this share of the other's (for saved sagas; the judge decides): 'Fairford' was in 42% of the
                      # bail story and 10% of the bombers-pulled one, which 30% on both sides kept apart (Oct 5)
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


# Before two stories first join a saga, the language model reads both side by side: sharing a name isn't enough when
# the name is an institution or a nationality (two separate cases at the Supreme Court, two separate plots by
# Iranian nationals both passed the word rule on Oct 4). Verdicts are cached by the headlines shown.
JUDGMENTS = os.path.join(Config.data, 'saga_judgments.json')
JUDGE_SAMPLE = 4  # headlines shown from each side
JUDGE_MODEL = 'qwen3:30b-a3b'  # the 8B said no to parts it called 'related cases, different outcomes' (Oct 5)
JUDGE_VERSION = 2  # verdicts cached under an older judge are asked again (hand verdicts are kept)
JUDGE_PROMPT = """Two groups of news headlines. Are they parts of one ongoing news story: the same case, incident, \
event, investigation or negotiation as it develops? Separate cases at the same court, separate crimes by people of the \
same nationality, or separate events involving the same person or place are different stories.

Group 1:
{a}

Group 2:
{b}

reason: one sentence
verdict: "one running story" or "separate stories\""""
# The same question worded the other way round. A link needs both wordings to say yes: one wording alone linked a
# British-Iranian man bailed over an RAF base plot with two Iranians charged over a plot against Jews (Oct 4)
JUDGE_PROMPT_B = """Group 1:
{a}

Group 2:
{b}

Would a news editor file these two groups under one running story: the same case, incident, event, investigation or \
negotiation, whether the groups report the same development of it or different developments? Answer no if they are \
two separate cases or events, even when they share a country, a court, a kind of crime or a person.

reason: one sentence
verdict: "one running story" or "separate stories\""""
# Worded verdicts after a reason with room to finish: cut off mid-reason (120, then 400 characters), or answering a
# bare true/false, the 30B said false after reasoning its way to 'the same developing story' (Cornell, Oct 5). The
# second wording said 'followed over time', which two groups on the same development aren't: it called them separate
JUDGE_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 1000},
                                                 "verdict": {"type": "string",
                                                             "enum": ["one running story", "separate stories"]}},
                "required": ["reason", "verdict"]}


def _ask(prompt: str) -> Optional[dict]:
    answer = llm.complete_json(prompt, JUDGE_SCHEMA, max_tokens=500, model=JUDGE_MODEL)
    if not answer or answer.get('verdict') not in JUDGE_SCHEMA['properties']['verdict']['enum']:
        return None
    return {'reason': answer.get('reason', ''), 'same_story': answer['verdict'] == 'one running story'}


def _sample(titles: list[str]) -> list[str]:
    distinct = list(dict.fromkeys(t.strip() for t in titles))
    picks = np.linspace(0, len(distinct) - 1, min(JUDGE_SAMPLE, len(distinct))).round().astype(int)
    return [distinct[i] for i in dict.fromkeys(picks)]


def same_saga(titles_a: list[str], titles_b: list[str]) -> bool:
    """Whether two groups of headlines are one running story, by the language model under two wordings, both of
    which must say yes (cached). False without an answer, so an unchecked link is never saved; the pair is asked
    again next run."""
    a, b = sorted([_sample(titles_a), _sample(titles_b)])
    key = hashlib.sha1(json.dumps([a, b]).encode()).hexdigest()
    cache = read_json(JUDGMENTS, {})
    entry = cache.get(key)
    if entry is None or not (entry.get('hand') or entry.get('judge') == JUDGE_VERSION):
        listed = {'a': '\n'.join(f'- {t}' for t in a), 'b': '\n'.join(f'- {t}' for t in b)}
        first = _ask(JUDGE_PROMPT.format(**listed))
        if first is None:
            return False
        second = None
        if first['same_story']:
            second = _ask(JUDGE_PROMPT_B.format(**listed))
            if second is None:
                return False
        entry = {**first, 'a': a, 'b': b, 'model': JUDGE_MODEL, 'judge': JUDGE_VERSION, 'second': second,
                 'same_story': bool(first['same_story'] and second and second['same_story'])}
        cache[key] = entry
        write_json(JUDGMENTS, cache)
        logger.info("Saga check: %s | %s -> %s (%s)", a[0], b[0], entry['same_story'],
                    (second or first).get('reason', ''))
    return bool(entry['same_story'])


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
           names_ok: set[str], titles: list[str]) -> dict:
    """Greedy saga merging (as in find_sagas) over `groups`: key -> {'members': [...], 'rows': [title rows]}. Two
    groups join only if they share a distinctive word that's a name (`names_ok`), in NAME_MIN_SHARE of one side's
    headlines and NAME_MIN_OTHER of the other's: sagas are kept for good, so a
    shared common noun ("rally") isn't enough to tie two stories together forever. And the language model has to
    agree they're one story (same_saga): a shared name can be an institution or a nationality."""
    def center(rows):
        v = vectors[rows].mean(axis=0)
        return v / np.linalg.norm(v)

    def shares(rows):
        """Each name rare on the day -> the share of these headlines that carry it"""
        counts = Counter(w for r in rows for w in bags[r] if w in names_ok and frequency[w] <= common)
        return {w: n / len(rows) for w, n in counts.items() if n >= NAME_MIN_OTHER * len(rows)}

    def distinctive(rows):
        return {w for w, share in shares(rows).items() if share >= NAME_MIN_SHARE}

    def shared(a, b):
        """A name in NAME_MIN_SHARE of one side's headlines and NAME_MIN_OTHER of the other's"""
        return any(max(names[a][w], names[b][w]) >= NAME_MIN_SHARE for w in names[a].keys() & names[b].keys())

    centers = {k: center(g['rows']) for k, g in groups.items()}
    names = {k: shares(g['rows']) for k, g in groups.items()}
    rejected = set()  # pairs of member sets the language model said aren't one story

    def pair(a, b):
        return frozenset([frozenset(groups[a]['members']), frozenset(groups[b]['members'])])
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
            if shared(a, b) and pair(a, b) not in rejected and \
                    (best is None or similarity[i, j] > best[0]):
                best = (similarity[i, j], a, b)
        if best is None:
            break
        _, a, b = best
        if not same_saga([titles[r] for r in groups[a]['rows']], [titles[r] for r in groups[b]['rows']]):
            rejected.add(pair(a, b))
            continue
        groups[a]['members'] += groups[b]['members']
        groups[a]['rows'] += groups[b]['rows']
        del groups[b], centers[b], names[b]
        centers[a], names[a] = center(groups[a]['rows']), shares(groups[a]['rows'])
    for k in groups:
        groups[k]['words'] = distinctive(groups[k]['rows'])
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
    groups = _merge(groups, vectors, bags, frequency, common, proper_nouns(titles), titles)

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


AGGREGATORS = {'Google News', 'Drudge Report', 'Real Clear Politics', 'Political Wire'}  # as in page_headlines
NOW_SLACK = td(minutes=30)  # a part seen this close to the latest run is on the front pages now
FIRST_RUN = td(minutes=15)  # headlines first seen this close together came in the same run


def history() -> list[dict]:
    """Every saved saga, for the tracker page: its parts in the order they broke (each with when it was on the front
    pages, its outlets and who had it first) and the outlets on any part by lean. Newest activity first. Times are
    UTC, naive, as stored."""
    with Session() as s:
        latest = s.query(Story.last_seen).order_by(Story.last_seen.desc()).limit(1).scalar()
        sagas = {g.id: g for g in s.query(Saga).all()}
        parts = s.query(Story).filter(Story.saga_id.isnot(None)).order_by(Story.first_seen).all()
        rows = s.query(StoryHeadline.story_id, Headline.title, Headline.first_accessed, Agency.name, Agency._bias,
                       Agency.lean_rated).join(Headline, Headline.id == StoryHeadline.headline_id) \
            .join(Article, Article.id == Headline.article_id).join(Agency, Agency.id == Article.agency_id) \
            .join(Story, Story.id == StoryHeadline.story_id).filter(Story.saga_id.isnot(None)).all()
        by_story = {}
        for story_id, title, first, agency, bias, rated in rows:
            if agency in AGGREGATORS:
                continue
            by_story.setdefault(story_id, []).append((first, agency, title.strip(), bias, rated))
        out = {}
        for p in parts:
            heads = sorted(by_story.get(p.id, []))
            saga = out.setdefault(p.saga_id, {'id': p.saga_id, 'name': sagas[p.saga_id].name if p.saga_id in sagas
                                              else None, 'parts': [], 'lean': {}})
            for _, agency, _, bias, rated in heads:
                saga['lean'][agency] = ('left' if bias < 0 else 'right' if bias > 0 else 'center') if rated else 'unrated'
            saga['parts'].append({
                'story': p.id, 'label': p.label or (heads[0][2] if heads else 'A part'), 'first': p.first_seen,
                'last': p.last_seen, 'now': latest is not None and p.last_seen >= latest - NOW_SLACK,
                'outlets': len({h[1] for h in heads}),
                # Every outlet that had it in the first run it was seen in: one run's headlines share a time, so
                # there's no telling which of them was first
                'first_outlets': sorted({h[1] for h in heads if h[0] - heads[0][0] <= FIRST_RUN}),
                'first_title': heads[0][2] if heads else None})
    for saga in out.values():
        saga['first'] = min(p['first'] for p in saga['parts'])
        saga['last'] = max(p['last'] for p in saga['parts'])
        saga['now'] = any(p['now'] for p in saga['parts'])
        sides = Counter(saga['lean'].values())
        saga.update({side: sides.get(side, 0) for side in ('left', 'center', 'right', 'unrated')})
        saga['outlets'] = len(saga.pop('lean'))
        saga['name'] = saga['name'] or saga['parts'][0]['label']
    return sorted(out.values(), key=lambda g: g['last'], reverse=True)
