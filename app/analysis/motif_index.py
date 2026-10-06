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
import functools
import hashlib
import os
import re
from datetime import datetime as dt

import numpy as np

from app.analysis import llm
from app.utils import Config, get_logger, store
from app.utils.store import read_json, write_json

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
# Naming sees the index first (Oct 5): named one claim at a time without it, 223 of 259 motifs held one claim
# ('Smug smirk', 'Houthi territorial expansion') and the same name was coined three times as separate entries
SHOWN = 8  # existing motifs shown when filing a claim, the closest to it (the user's motif was among the closest 8 for
# 77% of their settled claims, Oct 5)
# Filing judges the closest motifs side by side (Oct 6, after a bake-off on 60 of the user's settled claims: the old
# pick-or-name call to the 30B chose their motif for 37%; side by side, Gemma 4 26B for 57% with 54% of its picks
# theirs, at 2.4 s a claim; methods log and docs/models.md)
JUDGE_MODEL = 'gemma4:26b'
SHOWN_FLOOR = 0.45  # ...if at least this alike

NAME_PROMPT = """A claim people are telling or arguing over:
{claim}

Name the recurring rumor or narrative shapes it is an instance of: none to three, each a short reusable framing of \
three to seven words, terse like a folklorist's label or a proverb (a subject and what it does or is), without \
hedges such as "a claim that" or "is accused of": a shape that would fit the same kind of story told about \
other people, places or years. A story often \
carries more than one shape (who is blamed, what is feared, what is hoped); give each separately, the main one \
first, and don't pad: most claims have one or two. No names of people, places, organizations or dates. A framing \
people contest can name both sides of the dispute in one label. Judge the shapes as the tellers tell the story, not whether it's true. \
Check each name: would it still fit if the people and the event were different? If it only describes this one \
event, make it more general; if it would fit almost any story, make it more specific. A claim that only reports an \
event or states a fact, with no story told around it, has none: give an empty list rather than force one."""
NAME_SCHEMA = {"type": "object", "properties": {"motifs": {"type": "array", "minItems": 0, "maxItems": 3,
                                                          "items": {"type": "string", "maxLength": 60}}},
               "required": ["motifs"]}
REUSE_PROMPT = """Today is {today}. A claim people are telling or arguing over:
{claim}

Motifs in our index of recurring rumor and narrative shapes, each with some of the claims filed under it:
{options}

Which of these motifs is this claim clearly another instance of: the same kind of story as the claims filed under it, \
told about other people, places or years? Judge by what a motif's claims have in common, not by details only some of \
them share; a shared topic, person or place alone isn't enough. Most claims fit one or two; if none fits clearly, \
give none.

reason: a sentence or two
fits: the numbers of the motifs it clearly fits (none to three)"""

# Asked only when no motif fits: one question at a time (offering a new name in the same call as the judging made the
# judge pick the user's motif for 50% of their claims instead of 57%, Oct 6)
NEW_PROMPT = """A claim people are telling or arguing over:
{claim}

None of the motifs in our index of recurring rumor and narrative shapes fits it; the closest were: {closest}.

Does the claim tell a recurring story, the kind told again about other people, places or years? If it does, name it \
as a new motif: three to seven words, terse like a folklorist's label (a subject and what it does or is), no names of \
people, places, organizations or dates. If it only reports an event or states a fact, with no story told around it, \
give no name: don't force one.

reason: a sentence
new: the new motif's name, or nothing"""

MATCH_PROMPT = """A rumor shape: {phrase}
(from the claim: {claim})

Motifs already in our index, each with claims filed under it:
{options}

Is it the same motif as one of these: the same specific recurring shape, even if told about different people or \
events? A similar theme or a shared subject isn't enough: the claims should be the same kind of story. Give its \
number, or "new" if none of them is the same shape."""


MAX_WORDS = 7  # a longer 'name' is a sentence, usually the claim itself (an LAX kidnapping claim became one, Oct 5)


def clean(name: str) -> str:
    """A motif name without stray CJK characters (Qwen sometimes drifts into Chinese mid-phrase) or end punctuation."""
    return re.sub(r'[\u3000-\u9fff\uff00-\uffef]+', '', name).strip().rstrip('.,;:')


def key(claim: str) -> str:
    return hashlib.sha1(claim.strip().lower().encode()).hexdigest()[:16]


def load() -> dict:
    return read_json(INDEX, {'next': 1, 'entries': {}, 'claims': {}})


def save(index: dict):
    write_json(INDEX, index, indent=1)


def locked():
    """One writer at a time: the hourly filing and the organizer and motif check pages each read, change and save the
    whole index, so without this an edit made while a run was filing was lost when the run saved."""
    return store.locked(INDEX)


def exclusive(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        with locked():
            return fn(*args, **kwargs)
    return run


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


def described(entry: dict) -> str:
    """A motif as the model reads it when matching: its name, and its scope note, a person's or the model's draft (an
    evocative name, 'Leviathan', says less to the model than 'a giant sea creature menaces a ship')"""
    return entry['name'] + (f" ({entry['note']})" if entry.get('note') else '')


def live(index: dict) -> list[dict]:
    return [e for e in index['entries'].values() if not e.get('merged_into')]


def match(index: dict, phrase: str, claim: str) -> str | None:
    """The existing entry this shape is the same motif as, or None: the closest few by meaning, then the model's
    forced choice with "new" on offer."""
    from app.narratives import embed
    entries = [e for e in live(index) if key(claim) not in e.get('not_claims', [])]  # a person said it isn't
    if not entries:
        return None
    # Each entry by its name and its claims' phrases together, so a curated name still matches its kind
    texts = [described(e) + '. ' + '; '.join(e.get('phrases', [])[:5]) for e in entries]
    v = embed([phrase] + texts)
    sims = v[1:] @ v[0]
    top = [int(i) for i in np.argsort(-sims)[:CANDIDATES] if sims[i] >= MATCH_FLOOR]
    if not top:
        return None
    options = '\n'.join(f'{n}. {described(entries[i])} (e.g. ' + '; '.join(
        f'"{x["claim"][:110]}"' for x in entries[i]['claims'][-2:]) + ')' for n, i in enumerate(top, 1))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string", "maxLength": 1000},  # cut off mid-reason, the 30B answers no (as with sagas)
        "pick": {"type": "string", "enum": [str(n) for n in range(1, len(top) + 1)] + ['new']}},
        "required": ["reason", "pick"]}
    answer = llm.complete_json(MATCH_PROMPT.format(phrase=phrase, claim=claim, options=options), schema,
                               max_tokens=500, model=MODEL)
    return entries[top[int(answer['pick']) - 1]]['id'] if answer and answer['pick'] != 'new' else None


def closest(index: dict, claim: str) -> list[dict]:
    """The existing entries most like a claim, by meaning (its name, phrases and claims together), for naming it."""
    from app.narratives import embed
    entries = [e for e in live(index) if key(claim) not in e.get('not_claims', [])]  # a person said it isn't
    if not entries:
        return []
    texts = [described(e) + '. ' + '; '.join(e.get('phrases', [])[:5]) + '. ' + '; '.join(x['claim'][:120] for x in e['claims'][-2:])
             for e in entries]
    v = embed([claim] + texts)
    sims = v[1:] @ v[0]
    return [entries[int(i)] for i in np.argsort(-sims)[:SHOWN] if sims[i] >= SHOWN_FLOOR]


def name_claim(claim: str, shown: list[dict]) -> dict | None:
    """{'existing': [entries the judge filed it under], 'new': [a name for a shape none of them covers]}, or None.
    The closest motifs are judged side by side, each by its name, scope note and three of its claims; the picks come
    back as numbers (Qwen3.5 under Ollama returned an empty list of fixed strings, Oct 5)."""
    from datetime import datetime
    if not shown:
        named = llm.complete_json(NAME_PROMPT.format(claim=claim), NAME_SCHEMA, max_tokens=300, model=JUDGE_MODEL)
        return named and {'existing': [], 'new': [m for m in map(clean, named.get('motifs', [])) if fits_name(m)][:1]}
    options = '\n'.join(f'{n}. {described(e)}\n' + '\n'.join(f'   - {c["claim"][:160]}' for c in e['claims'][-3:])
                        for n, e in enumerate(shown, 1))
    schema = {"type": "object", "properties": {
        "reason": {"type": "string", "maxLength": 1000},
        "fits": {"type": "array", "maxItems": 3, "items": {"type": "integer", "minimum": 1, "maximum": len(shown)}}},
        "required": ["reason", "fits"]}
    answer = llm.complete_json(REUSE_PROMPT.format(today=datetime.now().strftime('%B %-d, %Y'), claim=claim,
                                                   options=options), schema, max_tokens=900, model=JUDGE_MODEL)
    if not answer:
        return None
    existing = [shown[n - 1] for n in dict.fromkeys(answer.get('fits', [])) if isinstance(n, int) and 1 <= n <= len(shown)][:3]
    if existing:
        return {'existing': existing, 'new': []}
    schema = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                               "new": {"type": "array", "maxItems": 1, "items": {"type": "string", "maxLength": 60}}},
              "required": ["reason", "new"]}
    named = llm.complete_json(NEW_PROMPT.format(claim=claim, closest='; '.join(e['name'] for e in shown[:5])), schema,
                              max_tokens=500, model=JUDGE_MODEL)
    if named is None:
        return None
    return {'existing': [], 'new': [m for m in map(clean, named.get('new', [])) if fits_name(m)]}


def fits_name(name: str) -> bool:
    return bool(name) and len(name.split()) <= MAX_WORDS


def same_name(index: dict, phrase: str) -> str | None:
    """An entry already called this (case and punctuation aside): one name, one motif"""
    norm = lambda t: re.sub(r'[^a-z0-9 ]', ' ', t.lower()).split()  # noqa: E731
    return next((e['id'] for e in live(index) if norm(e['name']) == norm(phrase)), None)


def file_claims(claims: list[dict], limit: int = MAX_NEW, budget: float | None = None) -> dict:
    """File each claim ({'claim', 'source': 'narrative' or a fact-checker's name, 'ref', 'side'}) under a motif,
    creating entries as needed. Claims already filed are left where they are. Returns the index."""
    index = load()
    todo = [c for c in claims if c.get('claim') and key(c['claim']) not in index['claims']][:limit]
    if not todo or llm.backend() is None:
        return index
    today = dt.now().strftime('%Y-%m-%d')
    import time
    started = time.time()
    for n, c in enumerate(todo):
        if budget is not None and time.time() - started > budget:
            break  # the next run picks up where this one stopped
        # One claim at a time on a fresh read of the index, saved as it goes: a run cut short keeps what it filed,
        # and an edit made on the organizer pages meanwhile isn't lost
        with locked():
            index = load()
            if key(c['claim']) in index['claims']:
                continue
            shown = closest(index, c['claim'])
            named = name_claim(c['claim'], shown)
            if not named:
                continue
            filed = [e['id'] for e in named['existing']]
            for e in named['existing']:
                entry = index['entries'][e['id']]
                entry['claims'].append({'claim': c['claim'], 'source': c.get('source', ''), 'ref': c.get('ref', ''),
                                        'side': c.get('side'), 'date': c.get('date') or today})
                entry['last_seen'] = max(entry.get('last_seen', ''), c.get('date') or today)
            for phrase in named['new'][:max(0, 3 - len(filed))]:
                eid = same_name(index, phrase) or match(index, phrase, c['claim'])
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


def nightly(budget: float | None = None):
    """File the latest report's narratives and the last 30 days' fact-checked claims not filed yet, for at most
    `budget` seconds."""
    from app.analysis import factchecks
    from app.site.page_folklore import latest_report
    claims = []
    from app.site.page_folklore import NOT_STORIES, withheld
    report = latest_report() or {}
    pulled = withheld()
    index = load()  # for corrected summaries
    for g in report.get('found', []):
        lab = g.get('label') or {}
        if lab.get('retold') and lab.get('narrative') and lab['narrative'] not in pulled and fits(lab):
            claims.append({'claim': corrected(lab['narrative'], index), 'source': 'narrative', 'ref': report.get('made', ''),
                           'side': g.get('shared_side'), 'date': (report.get('made') or '')[:10]})
    labels = factchecks.load_labels()
    for item in factchecks._items(factchecks.LABEL_DAYS):
        lab = labels.get(item['url']) or {}
        if lab.get('claim') and lab.get('genre') not in NOT_STORIES:  # a roundup or explainer checks no rumor
            claims.append({'claim': corrected(lab['claim'], index), 'source': item['source'], 'ref': item['url'],
                           'date': item['published'][:10]})
    from app.analysis import focus_group  # what voters say in focus groups: a source of its own
    claims += [{**c, 'claim': corrected(c['claim'], index)} for c in focus_group.claims()]
    import time
    started = time.time()
    index = file_claims(claims, budget=budget)
    # New motifs get the model's draft of a scope note (shown on the board to keep or edit; used in matching at once)
    gloss_missing(budget=None if budget is None else max(30, budget - (time.time() - started)))
    return index


def fits(label: dict) -> bool:
    """Whether a folklore group's claim belongs in the index. Political ones do, news included: news is powerful when it
    confirms a story people already tell (a Russian lab worker's plague death, told as a bioweapon). Other folklore
    does when it has a subject (contamination scares, legends), but not a shared topic, a sports pick or a game
    result (a Valkyries semifinal 'prophecy' got 'Valkyries to defeat Aces', Oct 5)."""
    from app.site.page_folklore import NOT_STORIES
    if label.get('genre') == 'none: a shared topic, not a retold narrative':
        return False
    if label.get('politics'):
        return True
    return label.get('genre') not in NOT_STORIES and label.get('family') not in (None, '', 'none')


# Curation, from the organizer on the label-check page (scripts/validate.py). A curated name is kept as given; a
# merged entry points to the one it joined, so its number still resolves; a deleted entry's claims are marked
# dropped (None), so the nightly filing leaves them out rather than filing them again.
SUGGEST = 0.72  # entry names at least this alike are suggested as merges
SUGGESTED = 15


@exclusive
def rename(eid: str, name: str):
    index = load()
    index['entries'][eid].update(name=clean(name), curated=True)
    save(index)


def _add(name: str) -> str:
    index = load()
    eid = f"M{index['next']:03d}"
    index['next'] += 1
    index['entries'][eid] = {'id': eid, 'name': clean(name), 'curated': True, 'claims': [], 'phrases': [],
                             'first_seen': dt.now().strftime('%Y-%m-%d')}
    save(index)
    return eid


@exclusive
def add(name: str) -> str:
    return _add(name)


@exclusive
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
    index['related'] = [sorted([target if x == source else x for x in p]) for p in index.get('related', [])]
    index['related'] = [p for i, p in enumerate(index['related']) if p[0] != p[1] and p not in index['related'][:i]]
    for e in index['entries'].values():  # its kinds become kinds of the motif it joined
        if source in parents_of(e):
            e['parents'] = [p for p in dict.fromkeys(target if p == source else p for p in parents_of(e)) if p != e['id']]
            e.pop('parent', None)
    for k in index['claims']:
        ids = [target if i == source else i for i in _ids(index, k)]
        index['claims'][k] = list(dict.fromkeys(ids))
    save(index)


@exclusive
def delete(eid: str):
    """Drop an entry: its claims keep their other motifs, and aren't filed again."""
    index = load()
    for k in index['claims']:
        index['claims'][k] = [i for i in _ids(index, k) if i != eid]
    del index['entries'][eid]
    save(index)


@exclusive
def move(claim: str, source: str, target: str):
    """Move one claim out of `source` into another entry (or a new one, target 'new')."""
    if target == 'new':
        target = _add(claim[:80])  # already holding the lock
    index = load()
    k = key(claim)
    entry = index['entries'][source]
    moved = [c for c in entry['claims'] if key(c['claim']) == k]
    entry['claims'] = [c for c in entry['claims'] if key(c['claim']) != k]
    entry.setdefault('not_claims', []).append(k)  # moved out by hand: it isn't this motif
    if not any(key(c['claim']) == k for c in index['entries'][target]['claims']):
        index['entries'][target]['claims'] += moved
    index['claims'][k] = list(dict.fromkeys([target if i == source else i for i in _ids(index, k)] + [target]))
    if not entry['claims'] and not entry.get('curated'):  # emptied: a motif the model made goes; one a person made stays
        del index['entries'][source]
    save(index)


@exclusive
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


def to_check(limit: int | None = None) -> list[dict]:
    """(claim, motif) filings nobody has checked yet, for the motif check page: the most-used motifs first (a wrong
    filing there spreads), then the rest."""
    out = []
    for e in sorted(live(load()), key=lambda e: (-len(e['claims']), e['id'])):
        for c in e['claims']:
            if not c.get('checked'):
                out.append({'id': e['id'], 'name': e['name'], 'size': len(e['claims']), 'claim': c['claim'],
                            'source': c.get('source', ''), 'others': [x['claim'] for x in e['claims'] if x is not c][:2]})
    return out[:limit] if limit else out


@exclusive
def check(claim: str, eid: str, answer: str):
    """A person's answer to 'is this claim an instance of this motif?', applied at once. Yes or not sure is noted on
    the filing. No takes the claim out of the motif and keeps it out; a motif the model made left with no claims goes
    (one a person named stays). A claim left with no motif stays without one: not every claim tells a recurring story,
    and filing it again forced it into some other motif (until Oct 5)."""
    index = load()
    entry = index['entries'].get(eid)
    found = next((c for c in (entry or {}).get('claims', []) if c['claim'] == claim), None)
    if found is None or answer not in ('yes', 'no', 'unsure'):
        raise ValueError(f'no such filing or answer: {eid} {answer}')
    if answer != 'no':
        found['checked'] = answer
    else:
        k = key(claim)
        entry['claims'].remove(found)
        entry.setdefault('not_claims', []).append(k)
        index['claims'][k] = [i for i in _ids(index, k) if i != eid]  # an empty list: no motif, and never refiled
        if not entry['claims'] and not entry.get('curated'):  # a model's motif emptied goes; one a person named stays
            del index['entries'][eid]
    save(index)


# Groups: a person's own chapters over the motifs (as Thompson grouped his into chapters), made on the motif board.
# Kept in the index: 'groups' (id -> name) and each entry's 'group'.

@exclusive
def group_add(name: str) -> str:
    index = load()
    groups = index.setdefault('groups', {})
    gid = f"G{max([int(g[1:]) for g in groups] + [0]) + 1:02d}"
    groups[gid] = {'id': gid, 'name': clean(name) or gid}
    save(index)
    return gid


@exclusive
def group_rename(gid: str, name: str):
    index = load()
    index['groups'][gid]['name'] = clean(name) or gid
    save(index)


@exclusive
def group_delete(gid: str):
    """The group goes; its motifs stay, ungrouped"""
    index = load()
    index.get('groups', {}).pop(gid, None)
    for e in index['entries'].values():
        if e.get('group') == gid:
            e.pop('group')
    save(index)


@exclusive
def group_assign(eid: str, gid: str | None):
    index = load()
    if gid and gid not in index.get('groups', {}):
        raise ValueError(f'no such group: {gid}')
    if gid:
        index['entries'][eid]['group'] = gid
    else:
        index['entries'][eid].pop('group', None)
    save(index)


@exclusive
def no_motif(claim: str):
    """A person says this claim tells no recurring story: out of every motif it was in, kept out, and never filed
    again (an empty filing). A model's motif left empty goes, as on a 'no' in the motif check."""
    index = load()
    k = key(claim)
    for eid in list(_ids(index, k)):
        entry = index['entries'].get(eid)
        if not entry:
            continue
        entry['claims'] = [c for c in entry['claims'] if c['claim'] != claim]
        entry.setdefault('not_claims', []).append(k)
        if not entry['claims'] and not entry.get('curated'):
            del index['entries'][eid]
    index['claims'][k] = []
    save(index)


@exclusive
def unfile(claim: str, eid: str):
    """Take a claim out of a motif for good (as a no on the motif check)"""
    check.__wrapped__(claim, eid, 'no')


def board() -> dict:
    """Everything the motif board shows: groups, and every live motif with its claims"""
    index = load()
    entries = [{'id': e['id'], 'name': e['name'], 'group': e.get('group'), 'curated': bool(e.get('curated')),
                'done': is_done(e), 'note': e.get('note', ''), 'note_by': e.get('note_by', 'person' if e.get('note') else ''),
                'parents': [p for p in parents_of(e) if p in index['entries'] and not index['entries'][p].get('merged_into')],
                'related': sorted({x for p in index.get('related', []) if e['id'] in p for x in p
                                   if x != e['id'] and x in index['entries'] and not index['entries'][x].get('merged_into')}),
                'first_seen': e.get('first_seen', ''), 'last_seen': e.get('last_seen', ''),
                # In a motif marked done, the claims that came in since (the ones to look at)
                'claims': [{'claim': c['claim'], 'source': c.get('source', ''), 'ref': c.get('ref', ''),
                            'checked': c.get('checked'), 'new': 'done' in e and key(c['claim']) not in e['done']}
                           for c in e['claims']]}
               for e in live(index)]
    return {'groups': list(index.get('groups', {}).values()), 'entries': entries}


@exclusive
def also_file(claim: str, source: str, target: str):
    """File a claim under another motif as well, keeping it where it is (a person's choice on the motif board)"""
    index = load()
    k = key(claim)
    found = next((c for c in index['entries'][source]['claims'] if key(c['claim']) == k), None)
    entry = index['entries'][target]
    if found is None or entry.get('merged_into'):
        raise ValueError(f'no such claim in {source}, or {target} is gone')
    if not any(key(c['claim']) == k for c in entry['claims']):
        entry['claims'].append({kk: v for kk, v in found.items() if kk != 'checked'})
    entry['not_claims'] = [x for x in entry.get('not_claims', []) if x != k]
    index['claims'][k] = list(dict.fromkeys(_ids(index, k) + [target]))
    save(index)


# Done marks from the motif board: a person working through the index hides each motif once they've looked it over.
# A motif is done while every claim it holds was there when it was marked; a new claim brings it back.

@exclusive
def mark_done(eid: str, done: bool = True):
    index = load()
    entry = index['entries'][eid]
    if done:
        entry['done'] = sorted(key(c['claim']) for c in entry['claims'])
    else:
        entry.pop('done', None)
    save(index)


@exclusive
def reset_done():
    index = load()
    for entry in index['entries'].values():
        entry.pop('done', None)
    save(index)


def is_done(entry: dict) -> str | None:
    """'done', 'new' (marked done, then a claim came in), or None"""
    if 'done' not in entry:
        return None
    return 'done' if {key(c['claim']) for c in entry['claims']} <= set(entry['done']) else 'new'


def similar(eid: str, n: int = 15) -> list[dict]:
    """The claims closest in meaning to a motif (its name and all its claims together), for adding by hand on the motif
    board: every claim in the index that isn't in it already and that a person hasn't said isn't it. Recomputed after
    each choice, so the motif's claims steer what comes next."""
    from app.narratives import embed
    index = load()
    entry = index['entries'][eid]
    have = {key(c['claim']) for c in entry['claims']}
    rejected = set(entry.get('not_claims', []))
    found = {}
    for e in live(index):
        for c in e['claims']:
            k = key(c['claim'])
            if k in have or k in rejected:
                continue
            item = found.setdefault(k, {'claim': c['claim'], 'source': c.get('source', ''), 'ref': c.get('ref', ''),
                                        'motifs': []})
            item['motifs'].append({'id': e['id'], 'name': e['name']})
    if not found:
        return []
    items = list(found.values())
    v = embed([entry['name'] + '. ' + '; '.join(c['claim'] for c in entry['claims'])] + [i['claim'] for i in items])
    sims = v[1:] @ v[0]
    for i, s in zip(items, sims):
        i['score'] = round(float(s), 3)
    return sorted(items, key=lambda i: -i['score'])[:n]


@exclusive
def reject(claim: str, eid: str):
    """A person says this claim isn't this motif: it's never suggested for it, or filed under it by the model"""
    index = load()
    entry = index['entries'][eid]
    k = key(claim)
    if k not in entry.setdefault('not_claims', []):
        entry['not_claims'].append(k)
    save(index)


# Kinds: a motif can be a kind of others ('Fake news fabrication' of both 'Misinformation spread' and 'Disinformation
# campaign'): a person's links between motifs, finer than groups, kept as each entry's 'parents'. Several parents, as in
# a thesaurus, not a tree; never a loop.

def parents_of(entry: dict) -> list[str]:
    """Its parents (entries saved with a single 'parent' before Oct 5 afternoon read as a list of one)"""
    return list(entry.get('parents') or ([entry['parent']] if entry.get('parent') else []))


@exclusive
def set_parent(eid: str, parent: str, on: bool = True):
    """`eid` is (on) or isn't (off) a kind of `parent`. Refuses a loop."""
    index = load()
    entries = index['entries']
    parents = parents_of(entries[eid])
    if on:
        if parent not in entries or entries[parent].get('merged_into') or parent == eid:
            raise ValueError(f'no such motif: {parent}')
        todo, seen = [parent], set()
        while todo:  # everything above the new parent must not include eid
            p = todo.pop()
            if p == eid:
                raise ValueError(f'{parent} is already a kind of {eid}')
            if p not in seen:
                seen.add(p)
                todo += parents_of(entries.get(p, {}))
        parents = list(dict.fromkeys(parents + [parent]))
        pair = sorted([eid, parent])  # related, so never suggested as a merge again
        if pair not in index.setdefault('not_same', []):
            index['not_same'].append(pair)
    else:
        parents = [p for p in parents if p != parent]
    entries[eid]['parents'] = parents
    entries[eid].pop('parent', None)
    save(index)


def shared_pairs(least: int = 2) -> list[dict]:
    """Motifs filed together on at least `least` of the same claims: candidates for being one motif (or one a kind of
    the other), judged by what they hold rather than by their names. Pairs a person kept apart, or linked as kinds,
    are left out. Most shared first."""
    from itertools import combinations
    index = load()
    entries = {e['id']: e for e in live(index)}
    apart = {tuple(sorted(p)) for p in index.get('not_same', [])}
    together = {}
    for k, ids in index['claims'].items():
        for a, b in combinations(sorted({i for i in ids if i in entries}), 2):
            together.setdefault((a, b), []).append(k)
    out = []
    for (a, b), keys in together.items():
        if len(keys) < least or (a, b) in apart or b in parents_of(entries[a]) or a in parents_of(entries[b]):
            continue
        text = {key(c['claim']): c['claim'] for c in entries[a]['claims'] + entries[b]['claims']}
        out.append({'a': a, 'b': b, 'shared': [text[k] for k in keys if k in text],
                    'only_a': [c['claim'] for c in entries[a]['claims'] if key(c['claim']) not in keys],
                    'only_b': [c['claim'] for c in entries[b]['claims'] if key(c['claim']) not in keys]})
    return sorted(out, key=lambda p: (-len(p['shared']), p['a']))


# Related: two motifs that belong near each other without being one, or one a kind of the other ('Rape accusation
# against men' and 'Campus sexual assault controversy' meet on some events and are different stories). Both ways.

@exclusive
def relate(a: str, b: str, related: bool = True):
    index = load()
    entries = index['entries']
    if a == b or a not in entries or b not in entries:
        raise ValueError(f'no such pair: {a} {b}')
    pair = sorted([a, b])
    links = index.setdefault('related', [])
    if related:
        if pair not in links:
            links.append(pair)
        if pair not in index.setdefault('not_same', []):  # related, so never suggested as one motif
            index['not_same'].append(pair)
    else:
        index['related'] = [p for p in links if p != pair]
    save(index)


# Corrected summaries: a person rewrites the model's one-line summary of a claim on the motif board. Kept in the index
# ('corrections': the model's wording -> the person's), so undo covers them, and applied wherever claims are read
# (the nightly filing, the Folklore and Rumors pages), so a corrected claim is never filed again in the old words.

def corrected(text: str, index: dict | None = None) -> str:
    fixes = (index if index is not None else load()).get('corrections', {})
    seen = set()
    while text in fixes and text not in seen:
        seen.add(text)
        text = fixes[text]
    return text


@exclusive
def correct_claim(old: str, new: str):
    new = ' '.join(new.split())
    index = load()
    ko, kn = key(old), key(new)
    if not new or new == old:
        return
    if ko not in index['claims']:
        raise ValueError('no such claim in the index')
    for e in index['entries'].values():
        for c in e['claims']:
            if key(c['claim']) == ko:
                c['claim'] = new
        if ko in e.get('not_claims', []):
            e['not_claims'] = [kn if k == ko else k for k in e['not_claims']]
        if ko in e.get('done', []):
            e['done'] = sorted({kn if k == ko else k for k in e['done']})
    ids = index['claims'].pop(ko)
    index['claims'][kn] = list(dict.fromkeys(index['claims'].get(kn, []) + ids))
    fixes = index.setdefault('corrections', {})
    for original, current in list(fixes.items()):  # an earlier correction of this claim now leads to the new words
        if current == old:
            fixes[original] = new
    fixes[old] = new
    save(index)


def originals(text: str, index: dict) -> set[str]:
    """Every wording that leads to `text` (itself included): to find a corrected claim in the reports and labels"""
    fixes = index.get('corrections', {})
    found, grew = {text}, True
    while grew:
        more = {o for o, c in fixes.items() if c in found} - found
        grew = bool(more)
        found |= more
    return found


def searchable_claims() -> list[dict]:
    """Every claim a person might file by hand: those in the index (with their motifs) and those the nightly filing
    would take but hasn't (the latest folklore report's, the last LABEL_DAYS of fact-checks), in today's words."""
    from app.analysis import factchecks
    from app.site.page_folklore import latest_report, withheld
    index = load()
    out = {}
    for e in live(index):
        for c in e['claims']:
            item = out.setdefault(key(c['claim']), {'claim': c['claim'], 'source': c.get('source', ''),
                                                    'ref': c.get('ref', ''), 'motifs': []})
            item['motifs'].append({'id': e['id'], 'name': e['name']})
    report = latest_report() or {}
    pulled = withheld()
    for g in report.get('found', []):
        lab = g.get('label') or {}
        if lab.get('narrative') and lab['narrative'] not in pulled:
            text = corrected(lab['narrative'], index)
            out.setdefault(key(text), {'claim': text, 'source': 'narrative', 'ref': report.get('made', ''), 'motifs': []})
    labels = factchecks.load_labels()
    for it in factchecks._items(factchecks.LABEL_DAYS):
        lab = labels.get(it['url']) or {}
        if lab.get('claim'):
            text = corrected(lab['claim'], index)
            out.setdefault(key(text), {'claim': text, 'source': it['source'], 'ref': it['url'], 'motifs': []})
    from app.analysis import focus_group
    for c in focus_group.claims():
        text = corrected(c['claim'], index)
        out.setdefault(key(text), {'claim': text, 'source': c['source'], 'ref': c['ref'], 'motifs': []})
    return list(out.values())


@exclusive
def file_by_hand(claim: dict, eid: str):
    """File a claim (one not in the index yet, or already elsewhere) under a motif a person chose"""
    index = load()
    entry = index['entries'][eid]
    if entry.get('merged_into'):
        raise ValueError(f'{eid} is gone')
    k = key(claim['claim'])
    if not any(key(c['claim']) == k for c in entry['claims']):
        entry['claims'].append({'claim': claim['claim'], 'source': claim.get('source', ''), 'ref': claim.get('ref', ''),
                                'date': dt.now().strftime('%Y-%m-%d')})
    entry['not_claims'] = [x for x in entry.get('not_claims', []) if x != k]
    index['claims'][k] = list(dict.fromkeys(index['claims'].get(k, []) + [eid]))
    save(index)


def single_suggestions(n: int = 5) -> list[dict]:
    """Every motif holding a single claim that a person hasn't said stands alone, with the motifs closest to its claim
    (by meaning: their names, phrases and claims) it might join, likeliest first. One embedding call for all."""
    from app.narratives import embed
    index = load()
    entries = live(index)
    # A single put in the hierarchy (a kind of another motif, or one with kinds of its own) has been placed, like one
    # that stands alone
    has_kinds = {p for e in entries for p in parents_of(e)}
    singles = [e for e in entries if len(e['claims']) == 1 and not e.get('stands_alone') and not parents_of(e)
               and e['id'] not in has_kinds]
    settled = {frozenset(p) for p in index.get('not_same', [])}  # kept apart, related or kinds: decided already
    if not singles:
        return []
    texts = [described(e) + '. ' + '; '.join(e.get('phrases', [])[:5]) + '. ' + '; '.join(c['claim'][:120] for c in e['claims'][-2:])
             for e in entries]
    v = embed([e['claims'][0]['claim'] for e in singles] + texts)
    claims_v, motifs_v = v[:len(singles)], v[len(singles):]
    out = []
    for e, cv in zip(singles, claims_v):
        k = key(e['claims'][0]['claim'])
        sims = motifs_v @ cv
        # Motifs already holding this very claim first: two names for one claim are the likeliest merge of all
        open_ = lambda m: m['id'] != e['id'] and frozenset([e['id'], m['id']]) not in settled  # noqa: E731
        siblings = [m for m in entries if open_(m) and any(key(c['claim']) == k for c in m['claims'])]
        picks = [(entries[i], float(sims[i])) for i in np.argsort(-sims)
                 if open_(entries[i]) and k not in entries[i].get('not_claims', [])
                 and not any(key(c['claim']) == k for c in entries[i]['claims'])][:n]
        out.append({'id': e['id'], 'name': e['name'], 'claim': e['claims'][0]['claim'],
                    'source': e['claims'][0].get('source', ''),
                    'suggest': [{'id': m['id'], 'name': m['name'], 'size': len(m['claims']), 'score': 1.0, 'same_claim': True}
                                for m in siblings] +
                               [{'id': m['id'], 'name': m['name'], 'size': len(m['claims']), 'score': round(s, 3)}
                                for m, s in picks]})
    return sorted(out, key=lambda s: -(s['suggest'][0]['score'] if s['suggest'] else 0))


@exclusive
def stands_alone(eid: str, alone: bool = True):
    """A person says this single-claim motif is right on its own: it leaves the singles list"""
    index = load()
    if alone:
        index['entries'][eid]['stands_alone'] = True
    else:
        index['entries'][eid].pop('stands_alone', None)
    save(index)


@exclusive
def set_note(eid: str, note: str):
    """A person's scope note for a motif: one plain line on what it covers, beside its name (used in matching and
    shown on the site); empty removes it"""
    index = load()
    note = ' '.join(note.split())
    entry = index['entries'][eid]
    if note:
        entry['note'], entry['note_by'] = note, 'person'
    else:
        entry.pop('note', None)
        entry.pop('note_by', None)
    save(index)


def keep_note(eid: str):
    """A person keeps the model's drafted note as it is: it's theirs now, and shown on the site"""
    index = load()
    if index['entries'][eid].get('note'):
        index['entries'][eid]['note_by'] = 'person'
        save(index)


DRAFTS = ('model', 'claude')  # notes drafted, not yet kept: the local model's, or the Oct 5 one-off backfill by Claude


def public_note(entry: dict) -> str:
    """The note the site shows: a person's (written or kept), never a draft"""
    return entry.get('note', '') if entry.get('note') and entry.get('note_by') not in DRAFTS else ''


GLOSS_PROMPT = """A motif in our index of recurring rumor and narrative shapes: {name}
Claims people are telling that are filed under it:
{claims}

common: first, in a sentence or two, what these claims have in common as stories: who does what to whom, as the \
people telling them tell it. Look past the particular events to the kind of story. The motif's name is the main \
guide (a person chose many of them): with only one or two claims, take the kind of story from the name, and use the \
claims only to see how it is told.
note: then the motif's scope note: one plain sentence saying what kind of story this motif covers, built from what \
they have in common. Write it the way its tellers tell it, as if it were so; never judge it (no "false", \
"misleading", "debunked", "claims that" or "alleged"). Use kinds of people and places, not particular ones, unless \
the motif's own name names them: then it is a named narrative, and the note keeps that name. Start with what \
happens, not with "This motif", "A motif" or "Stories"."""
GLOSS_SCHEMA = {"type": "object", "properties": {"common": {"type": "string", "maxLength": 500},
                                                 "note": {"type": "string", "maxLength": 320}},
                "required": ["common", "note"]}
GLOSS_CLAIMS = 8  # claims shown when drafting a note
GLOSS_MIN = 3  # claims a motif needs before the model drafts its note: with one or two it restated them (Oct 5)


VERDICT_WORDS = re.compile(r"\b(false|falsely|misleading|debunked|unfounded|baseless|claims? that|alleged(ly)?|"
                           r"misinformation|disinformation|conspiracy theor)", re.I)


def gloss(entry: dict) -> str | None:
    """The model's draft of a motif's scope note, from its name and claims: the story as its tellers tell it. A draft
    that judges the story (fact-check summaries pull it toward "falsely attributed") or names people or places is
    asked for again, twice at most, then left for a person. Motifs whose names are themselves about falsehood (Fake news) may say so: their name is the story."""
    claims = '\n'.join(f'- {c["claim"][:180]}' for c in entry['claims'][-GLOSS_CLAIMS:]) or '(none yet)'
    prompt = GLOSS_PROMPT.format(name=entry['name'], claims=claims)
    about_falsehood = re.search(r'\b(fake|false|lie|lies|hoax|disinformation|misinformation|propaganda)\b', entry['name'], re.I)
    for attempt in range(3):
        answer = llm.complete_json(prompt, GLOSS_SCHEMA, max_tokens=600, model=MODEL)
        note = ' '.join((answer or {}).get('note', '').split())
        if not note or note[-1] not in '.!?"\u201d':
            continue  # none, or cut off at the length limit mid-sentence
        if re.search(r'\b(the user|scope note|motif)\b', note, re.I):
            continue  # the model talking about the task, not answering it
        judged = VERDICT_WORDS.search(note) and not about_falsehood
        own = {w.lower() for w in re.findall(r"[\w'-]+", entry['name'])}  # a named narrative keeps its names
        named = [w for w in names_in(note) if w.lower() not in own]
        if not judged and not named:
            return note
        prompt += ('\n\nYour last answer: "' + note + '". ' + ('It judged the story: say only what the people telling '
                   'it say happens. ' if judged else '') + (f'It named {", ".join(named)}: say what they are instead.'
                                                            if named else ''))
    return None


def names_in(text: str) -> list[str]:
    """Capitalized words past the first that aren't sentence starts: names, which a scope note shouldn't have"""
    words = re.findall(r"[A-Za-z][\w'-]*", text)
    return [w for i, w in enumerate(words[1:], 1) if w[0].isupper() and w not in ('I',)
            and not re.search(r'[.!?]\s+' + re.escape(w), text)]


def needs_gloss(entry: dict) -> bool:
    """A motif with GLOSS_MIN claims and no note, or a model draft from when it held half as many claims or fewer.
    A person's note (written or kept) is never redrafted."""
    n = len(entry['claims'])
    if n < GLOSS_MIN:
        return False
    if not entry.get('note'):
        return True
    return entry.get('note_by') == 'model' and n >= 2 * entry.get('note_claims', n)


def gloss_missing(budget: float | None = None) -> int:
    """Draft notes for the motifs that need one (needs_gloss), for at most `budget` seconds; how many were drafted"""
    import time
    started, done = time.time(), 0
    for eid in [e['id'] for e in live(load()) if needs_gloss(e)]:
        if budget is not None and time.time() - started > budget:
            break
        entry = load()['entries'][eid]
        note = gloss(entry)
        if not note:
            continue
        with locked():
            index = load()
            e = index['entries'].get(eid)
            if e and needs_gloss(e):  # a person may have written one meanwhile
                e['note'], e['note_by'], e['note_claims'] = note, 'model', len(e['claims'])
                save(index)
                done += 1
    if done:
        logger.info("Motif index: drafted %d scope notes", done)
    return done
