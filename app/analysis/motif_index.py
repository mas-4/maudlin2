"""Our own motif index (#145): the recurring shapes of the rumors and narratives we see, built as we go, the way
Thompson built his from the tales he read, but from today's political talk. Thompson's index is built from folktales
and fits modern political rumor badly (Oct 4: a strict reading matched a specific motif for 5 of 151 claims), so it
isn't shown; this one grows from what we actually find.

Each claim (a folklore narrative's, or one a fact-checker examined) gets a motif phrase from the model: the rumor's
shape as a reusable framing, with no names, places or dates, so the same story told about other people or another
year lands in the same entry ("the ruler is senile", "a group votes as one bloc"). The phrase is matched against the
entries we have (the closest few by meaning, then the model's forced choice with "new" on offer); if none fits, it
becomes a new entry. Entries are numbered M001, M002… and keep their claims, first and last sighting and sources.
Refined by hand on the label-check page (rename, merge), where the entries' names become curated.

A claim can carry up to three motifs (a story is often several shapes at once: who's blamed, what's feared, what's
hoped), each filed on its own. Stored in data/motif_index.json:
{'next': 3, 'entries': {'M001': {...}}, 'claims': {claim key: [entry ids]}} (an empty list: filed, no motif kept)."""
import hashlib
import json
import os
import re
from datetime import datetime as dt

import numpy as np

from app.analysis import llm
from app.utils import Config, get_logger

logger = get_logger(__name__)

INDEX = os.path.join(Config.data, 'motif_index.json')
# Naming a shape and judging whether two claims are the same shape are the hard calls, and only about a hundred
# claims come in a night, so they go to the bigger local model (a mixture of experts, partly on the CPU)
MODEL = 'qwen3:30b-a3b'
CANDIDATES = 5
# Entries less alike than this aren't offered. Oct 5, with the 8B judging: good merges' phrases were 0.77-0.86 alike,
# most bad ones 0.71-0.75 (0.6 let vague early entries snowball); the 30B judges the 0.7-0.76 band. A missed merge
# is easier to fix by hand than a wrong one
MATCH_FLOOR = 0.7
MAX_NEW = 200  # claims filed a run, at most

NAME_PROMPT = """A claim people are telling or arguing over:
{claim}

Name the recurring rumor or narrative shapes it is an instance of: one to three, each a reusable framing in under \
ten words, a shape that would fit the same kind of story told about other people, places or years. A story often \
carries more than one shape (who is blamed, what is feared, what is hoped); give each separately, the main one \
first, and don't pad: most claims have one or two. No names of people, places, organizations or dates. A contested \
framing can be two-sided ("X is / isn't Y"). Judge the shapes as the tellers tell the story, not whether it's true. \
Check each name: would it still fit if the people and the event were different? If it only describes this one \
event, make it more general; if it would fit almost any story, make it more specific."""
NAME_SCHEMA = {"type": "object", "properties": {"motifs": {"type": "array", "minItems": 1, "maxItems": 3,
                                                          "items": {"type": "string", "maxLength": 80}}},
               "required": ["motifs"]}
MATCH_PROMPT = """A rumor shape: {phrase}
(from the claim: {claim})

Motifs already in our index, each with claims filed under it:
{options}

Is it the same motif as one of these: the same specific recurring shape, even if told about different people or \
events? A similar theme or a shared subject isn't enough: the claims should be the same kind of story. Give its \
number, or "new" if none of them is the same shape."""


def clean(name: str) -> str:
    """A motif name without stray CJK characters (Qwen sometimes drifts into Chinese mid-phrase) or end punctuation."""
    return re.sub(r'[\u3000-\u9fff\uff00-\uffef]+', '', name).strip().rstrip('.,;:')


def key(claim: str) -> str:
    return hashlib.sha1(claim.strip().lower().encode()).hexdigest()[:16]


def load() -> dict:
    try:
        with open(INDEX) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {'next': 1, 'entries': {}, 'claims': {}}


def save(index: dict):
    with open(INDEX, 'w') as f:
        json.dump(index, f, indent=1)


def _ids(index: dict, claim_key: str) -> list[str]:
    ids = index['claims'].get(claim_key) or []
    return [ids] if isinstance(ids, str) else list(ids)  # one id: an index from before claims had several


def resolve(index: dict, eid: str) -> str:
    while eid in index['entries'] and index['entries'][eid].get('merged_into'):
        eid = index['entries'][eid]['merged_into']
    return eid


def entries_of(index: dict, claim: str) -> list[dict]:
    """The entries a claim is filed under (following merges), main motif first."""
    out = []
    for eid in _ids(index, key(claim)):
        eid = resolve(index, eid)
        if eid in index['entries'] and index['entries'][eid] not in out:
            out.append(index['entries'][eid])
    return out


def entry_of(index: dict, claim: str) -> dict | None:
    """The claim's main motif, or None."""
    found = entries_of(index, claim)
    return found[0] if found else None


def live(index: dict) -> list[dict]:
    return [e for e in index['entries'].values() if not e.get('merged_into')]


def match(index: dict, phrase: str, claim: str) -> str | None:
    """The existing entry this shape is the same motif as, or None: the closest few by meaning, then the model's
    forced choice with "new" on offer."""
    from app.narratives import embed
    entries = live(index)
    if not entries:
        return None
    # Each entry by its name and its claims' phrases together, so a curated name still matches its kind
    texts = [e['name'] + '. ' + '; '.join(e.get('phrases', [])[:5]) for e in entries]
    v = embed([phrase] + texts)
    sims = v[1:] @ v[0]
    top = [int(i) for i in np.argsort(-sims)[:CANDIDATES] if sims[i] >= MATCH_FLOOR]
    if not top:
        return None
    options = '\n'.join(f'{n}. {entries[i]["name"]} (e.g. ' + '; '.join(
        f'"{x["claim"][:110]}"' for x in entries[i]['claims'][-2:]) + ')' for n, i in enumerate(top, 1))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string", "maxLength": 200},
        "pick": {"type": "string", "enum": [str(n) for n in range(1, len(top) + 1)] + ['new']}},
        "required": ["reason", "pick"]}
    answer = llm.complete_json(MATCH_PROMPT.format(phrase=phrase, claim=claim, options=options), schema,
                               max_tokens=160, model=MODEL)
    return entries[top[int(answer['pick']) - 1]]['id'] if answer and answer['pick'] != 'new' else None


def file_claims(claims: list[dict], limit: int = MAX_NEW) -> dict:
    """File each claim ({'claim', 'source': 'narrative' or a fact-checker's name, 'ref', 'side'}) under a motif,
    creating entries as needed. Claims already filed are left where they are. Returns the index."""
    index = load()
    todo = [c for c in claims if c.get('claim') and key(c['claim']) not in index['claims']][:limit]
    if not todo or llm.backend() is None:
        return index
    today = dt.now().strftime('%Y-%m-%d')
    for c in todo:
        named = llm.complete_json(NAME_PROMPT.format(claim=c['claim']), NAME_SCHEMA, max_tokens=160, model=MODEL)
        if not named:
            continue
        filed = []
        for phrase in dict.fromkeys(clean(m) for m in named.get('motifs', []) if clean(m)):
            eid = match(index, phrase, c['claim'])
            if eid in filed:
                continue
            if eid is None:
                eid = f"M{index['next']:03d}"
                index['next'] += 1
                index['entries'][eid] = {'id': eid, 'name': phrase, 'curated': False, 'first_seen': today,
                                         'claims': [], 'phrases': []}
            entry = index['entries'][eid]
            entry['claims'].append({'claim': c['claim'], 'source': c.get('source', ''), 'ref': c.get('ref', ''),
                                    'side': c.get('side'), 'date': c.get('date') or today})
            entry['phrases'] = (entry.get('phrases', []) + [phrase])[-20:]
            entry['last_seen'] = max(entry.get('last_seen', ''), c.get('date') or today)
            filed.append(eid)
        index['claims'][key(c['claim'])] = filed
    save(index)
    logger.info("Motif index: filed %d claims; %d motifs", len(todo), len(live(index)))
    return index


def nightly():
    """File the latest report's narratives and the last 30 days' fact-checked claims."""
    from app.analysis import factchecks
    from app.site.page_folklore import latest_report
    claims = []
    from app.site.page_folklore import NOT_STORIES, withheld
    report = latest_report() or {}
    pulled = withheld()
    for g in report.get('found', []):
        lab = g.get('label') or {}
        # Retold narratives only: not news reactions or shared topics, nothing withheld by hand
        if lab.get('retold') and lab.get('narrative') and lab.get('genre') not in NOT_STORIES \
                and lab['narrative'] not in pulled:
            claims.append({'claim': lab['narrative'], 'source': 'narrative', 'ref': report.get('made', ''),
                           'side': g.get('shared_side'), 'date': (report.get('made') or '')[:10]})
    labels = factchecks.load_labels()
    for item in factchecks._items(factchecks.LABEL_DAYS):
        lab = labels.get(item['url']) or {}
        if lab.get('claim') and lab.get('genre') not in NOT_STORIES:  # a roundup or explainer checks no rumor
            claims.append({'claim': lab['claim'], 'source': item['source'], 'ref': item['url'],
                           'date': item['published'][:10]})
    return file_claims(claims)


# Curation, from the organizer on the label-check page (scripts/validate.py). A curated name is kept as given; a
# merged entry points to the one it joined, so its number still resolves; a deleted entry's claims are marked
# dropped (None), so the nightly filing leaves them out rather than filing them again.
SUGGEST = 0.72  # entry names at least this alike are suggested as merges
SUGGESTED = 15


def rename(eid: str, name: str):
    index = load()
    index['entries'][eid].update(name=clean(name), curated=True)
    save(index)


def add(name: str) -> str:
    index = load()
    eid = f"M{index['next']:03d}"
    index['next'] += 1
    index['entries'][eid] = {'id': eid, 'name': clean(name), 'curated': True, 'claims': [], 'phrases': [],
                             'first_seen': dt.now().strftime('%Y-%m-%d')}
    save(index)
    return eid


def merge(source: str, target: str):
    """Fold `source` into `target`: its claims and phrases move over (a claim in both counts once), and its number
    points to `target`."""
    index = load()
    if source == target:
        return
    src, dst = index['entries'][source], index['entries'][target]
    have = {key(c['claim']) for c in dst['claims']}
    dst['claims'] += [c for c in src['claims'] if key(c['claim']) not in have]
    dst['phrases'] = (dst.get('phrases', []) + src.get('phrases', []))[-20:]
    dst['first_seen'] = min(filter(None, [dst.get('first_seen'), src.get('first_seen')]), default=None)
    dst['last_seen'] = max(filter(None, [dst.get('last_seen'), src.get('last_seen')]), default=None)
    src.update(claims=[], merged_into=target)
    for k in index['claims']:
        ids = [target if i == source else i for i in _ids(index, k)]
        index['claims'][k] = list(dict.fromkeys(ids))
    save(index)


def delete(eid: str):
    """Drop an entry: its claims keep their other motifs, and aren't filed again."""
    index = load()
    for k in index['claims']:
        index['claims'][k] = [i for i in _ids(index, k) if i != eid]
    del index['entries'][eid]
    save(index)


def move(claim: str, source: str, target: str):
    """Move one claim out of `source` into another entry (or a new one, target 'new')."""
    if target == 'new':
        target = add(claim[:80])
    index = load()
    k = key(claim)
    entry = index['entries'][source]
    moved = [c for c in entry['claims'] if key(c['claim']) == k]
    entry['claims'] = [c for c in entry['claims'] if key(c['claim']) != k]
    if not any(key(c['claim']) == k for c in index['entries'][target]['claims']):
        index['entries'][target]['claims'] += moved
    index['claims'][k] = list(dict.fromkeys([target if i == source else i for i in _ids(index, k)] + [target]))
    save(index)


def not_same(a: str, b: str):
    """Remember that two entries aren't the same motif, so they're not suggested again."""
    index = load()
    index.setdefault('not_same', []).append(sorted([a, b]))
    save(index)


def suggestions(limit: int = SUGGESTED) -> list[tuple[str, str, float]]:
    """Pairs of live entries whose names are most alike, likely the same motif: (id, id, similarity)."""
    from app.narratives import embed
    index = load()
    entries = live(index)
    if len(entries) < 2:
        return []
    v = embed([e['name'] for e in entries])
    sims = v @ v.T
    dismissed = {tuple(p) for p in index.get('not_same', [])}
    pairs = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = sorted([entries[i]['id'], entries[j]['id']])
            if sims[i, j] >= SUGGEST and (a, b) not in dismissed:
                pairs.append((a, b, float(sims[i, j])))
    return sorted(pairs, key=lambda p: -p[2])[:limit]
