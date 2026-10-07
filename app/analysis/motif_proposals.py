"""The correction proposer (Oct 7): the bigger local model reads over the motif index and proposes small fixes, each
one atomic change a person approves or rejects in the workbench's 💡 proposals checklist:

  rename   a typo in a motif's name ("Poltiicians' empty promises")
  note     a typo in its scope note
  parent   one motif is a kind of another
  relate   two motifs are related (told together, close cousins)
  merge    two motifs are the same one
  group    a motif belongs in one of the person's groups
  unrelate two motifs linked as related aren't (a review of the links already made)
  unparent a motif linked as a kind of another isn't

Approving runs the same action the person would (logged, undoable); a decision is kept, so a rejected proposal never
comes back. Candidates are found cheaply (motifs close in meaning, motifs sharing a claim, motifs near a group's
members) and only those are put to the model. It runs nightly (nightly(), from the hourly run once the morning's
report and its first filings are in), a few minutes at most; or by hand (scripts/propose_motif_fixes.py).

The model's own "no" (two motifs unrelated, a motif not in a group) and its typo reading are kept with a mark of the
motifs as they were (name, note, about how many claims): when a motif changes, it's asked about again. A person's
decision is never asked again.

Best fit (Oct 7): a second read of each kind-of and related proposal by the same model, shown some of the person's own
decisions on such links, scores it 0-10 (judge()); a small model trained on the person's decisions (best_fit()) weighs
that score with plain facts about the two motifs (how alike their descriptions and claims are, claims and genre
shared, groups apart) into a best fit, by which the checklist is sorted. Those least likely to be approved are folded
away at the bottom, nothing hidden. On the person's first 144 decisions, held out: folding the lowest put 29 of 65
rejected ones there and 8 of 79 approved (the judge alone did worse: it scored most of both 2 or 3)."""
import difflib
import hashlib
import json
import os
from datetime import datetime as dt

import numpy as np

from app.analysis import llm
from app.analysis import motif_index as mi
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

PROPOSALS = os.path.join(Config.data, 'motif_proposals.json')  # {id: proposal}, decided ones kept for good
RUNS = os.path.join(Config.data, 'motif_proposals_runs.json')  # {'done': last day finished, 'typos': {motif: mark}}
NIGHT_BUDGET = 480  # seconds the nightly run may spend; what's left waits for the next hour's run
MODEL = 'gemma4:26b'
TYPO_BATCH = 12  # motifs read in one call for typos
LINK_NEIGHBORS = 5  # each motif's closest motifs considered for a link
LINK_FLOOR = 0.7  # ...at least this alike (mxbai, over name, note and claims)
MAX_PAIRS = 120  # pairs put to the model in one run, the most alike first
GROUP_CANDIDATES = 12  # motifs near a group's members asked about, per group
GROUP_FLOOR = 0.6
TYPO_SIMILARITY = 0.8  # a fix must leave the text this alike (difflib): a typo, not a rewrite
MERGE_FLOOR = 0.8  # a merge is proposed only for motifs this alike in meaning (the first run proposed merging motifs
# that merely shared a claim: "Watermelon" and "Trojan horse")
SHARED_FLOOR = 0.6  # motifs sharing a single claim are asked about only if this alike; two or more shared, always
JUDGED = ('relate', 'parent')  # the kinds the judge scores and best fit sorts
JUDGE_EXAMPLES = 8  # of the person's past decisions on that kind of link, shown to the judge: this many kept, this many rejected
FIT_MIN = 30  # decisions needed before best fit is trained
FIT_KEEP = 0.9  # the fold: below the best fit that keeps this share of the person's approved proposals above it


def mark(e: dict) -> str:
    """A motif as the model last saw it: its name, note and about how many claims (doubling counts as a change)"""
    import math
    return hashlib.sha1(json.dumps([e['name'], e.get('note', ''), int(math.log2(len(e['claims']) + 1))]).encode()).hexdigest()[:8]


class Spent(Exception):
    """The run's time is up"""


def pid(kind: str, args: dict) -> str:
    return hashlib.sha1(json.dumps([kind, args], sort_keys=True).encode()).hexdigest()[:10]


def load() -> dict:
    return read_json(PROPOSALS, {})


def save(store: dict):
    """A run's store written back over what's on disk now: a person's decisions made meanwhile (in the checker) stay;
    the run adds its new proposals and its scores"""
    disk = load()
    for i, p in store.items():
        if i in disk and disk[i].get('status') in ('approved', 'rejected'):
            disk[i] = {**p, 'status': disk[i]['status'], 'decided': disk[i].get('decided')}
        else:
            disk[i] = p
    write_json(PROPOSALS, disk)


def add(store: dict, kind: str, args: dict, reason: str) -> bool:
    """A new proposal, unless the same one was made before (open or decided)"""
    i = pid(kind, args)
    if i in store:
        return False
    store[i] = {'id': i, 'kind': kind, 'args': args, 'reason': reason, 'model': MODEL,
                'made': dt.now().isoformat(timespec='seconds'), 'status': 'open'}
    return True


def still_holds(p: dict, index: dict) -> bool:
    """Whether an open proposal still makes sense: its motifs live and the change not made (or overtaken) since"""
    entries, a = index['entries'], p['args']
    live = lambda i: i in entries and not entries[i].get('merged_into')  # noqa: E731
    k = p['kind']
    if k == 'rename':
        return live(a['id']) and entries[a['id']]['name'] == a['from'] and a['to'] != a['from']
    if k == 'note':
        return live(a['id']) and (entries[a['id']].get('note') or '') == a['from'] and a['to'] != a['from']
    if k == 'parent':
        return live(a['id']) and live(a['parent']) and a['parent'] not in mi.parents_of(entries[a['id']]) \
            and a['id'] not in mi.parents_of(entries[a['parent']]) and not mi.genres_clash(entries[a['id']], entries[a['parent']])
    if k in ('relate', 'merge'):
        pair = sorted([a['a'], a['b']])
        return live(a['a']) and live(a['b']) and pair not in index.get('related', []) \
            and not (k == 'merge' and pair in index.get('not_same', []))
    if k == 'group':
        return live(a['id']) and a['group'] in index.get('groups', {}) and a['group'] not in mi.groups_of(entries[a['id']])
    if k == 'unrelate':
        return live(a['a']) and live(a['b']) and sorted([a['a'], a['b']]) in index.get('related', [])
    if k == 'unparent':
        return live(a['id']) and live(a['parent']) and a['parent'] in mi.parents_of(entries[a['id']])
    return False


KINDS = ['rename', 'note', 'merge', 'unparent', 'unrelate', 'parent', 'relate', 'group']  # the checklist's order


def open_proposals() -> list[dict]:
    """The checklist: typo fixes, merges and link removals first (in KINDS order), then the kind-of and related
    proposals together, best fit first; each of those below the fold's cut marked 'unlikely'"""
    index = mi.load()
    cut = (read_json(RUNS, {}).get('fit') or {}).get('cut')
    out = []
    for p in load().values():
        if p['status'] == 'open' and still_holds(p, index):
            fit = p.get('fit') if p['kind'] in JUDGED else None
            out.append({**p, 'unlikely': fit is not None and cut is not None and fit < cut})
    first = len([k for k in KINDS if k not in JUDGED])
    return sorted(out, key=lambda p: (KINDS.index(p['kind']) if p['kind'] not in JUDGED else first,
                                      -(p.get('fit') if p.get('fit') is not None else -1), p['made']))


def decide(proposal_id: str, decision: str):
    store = load()
    if proposal_id not in store or decision not in ('approved', 'rejected'):
        raise ValueError(f'no such proposal or decision: {proposal_id} {decision}')
    store[proposal_id].update(status=decision, decided=dt.now().isoformat(timespec='seconds'))
    write_json(PROPOSALS, store)


def action(p: dict) -> dict:
    """The workbench action that carries out a proposal"""
    a = p['args']
    return {'rename': {'action': 'rename', 'id': a.get('id'), 'name': a.get('to')},
            'note': {'action': 'note', 'id': a.get('id'), 'note': a.get('to')},
            'parent': {'action': 'parent', 'id': a.get('id'), 'parent': a.get('parent'), 'on': True},
            'relate': {'action': 'relate', 'a': a.get('a'), 'b': a.get('b')},
            'merge': {'action': 'merge', 'source': a.get('a'), 'target': a.get('b')},
            'group': {'action': 'group_member', 'id': a.get('id'), 'group': a.get('group'), 'on': True},
            'unrelate': {'action': 'unrelate', 'a': a.get('a'), 'b': a.get('b')},
            'unparent': {'action': 'parent', 'id': a.get('id'), 'parent': a.get('parent'), 'on': False}}[p['kind']]


# ---------- typos ----------
TYPO_PROMPT = """Motifs in our index of rumor and narrative shapes, each a name and maybe a scope note:
{motifs}

Find typos only: misspelled words, letters swapped or doubled, a missing or repeated word, wrong capitalization of a \
proper noun. Don't reword, shorten, restyle or improve anything, and leave a name's sentence case alone. For each \
motif with a typo, give its number and its name and note written out in full with only the typo fixed. Most have none.

fixes: the motifs with typos (often none)"""
TYPO_SCHEMA = {"type": "object", "properties": {"fixes": {"type": "array", "maxItems": TYPO_BATCH, "items": {
    "type": "object", "properties": {"n": {"type": "integer"}, "name": {"type": "string", "maxLength": 120},
                                     "note": {"type": "string", "maxLength": 400}},
    "required": ["n", "name", "note"]}}}, "required": ["fixes"]}


def small_fix(old: str, new: str) -> bool:
    new = ' '.join((new or '').split())
    return bool(old) and bool(new) and new != old and difflib.SequenceMatcher(None, old, new).ratio() >= TYPO_SIMILARITY


def typos(store: dict, index: dict, runs: dict | None = None, deadline: float | None = None) -> int:
    """Typos in the motifs not read since they last changed"""
    import time
    made = 0
    runs = runs if runs is not None else {}
    read = runs.setdefault('typos', {})
    entries = [e for e in mi.live(index) if read.get(e['id']) != mark(e)]
    for start in range(0, len(entries), TYPO_BATCH):
        if deadline and time.time() > deadline:
            raise Spent
        batch = entries[start:start + TYPO_BATCH]
        listing = '\n'.join(f'{n}. name: {e["name"]}' + (f'\n   note: {e["note"]}' if e.get('note') else '')
                            for n, e in enumerate(batch, 1))
        answer = llm.complete_json(TYPO_PROMPT.format(motifs=listing), TYPO_SCHEMA, max_tokens=1500, model=MODEL)
        for fix in (answer or {}).get('fixes', []):
            if not (isinstance(fix.get('n'), int) and 1 <= fix['n'] <= len(batch)):
                continue
            e = batch[fix['n'] - 1]
            name = ' '.join((fix.get('name') or '').split())
            if small_fix(e['name'], name):
                made += add(store, 'rename', {'id': e['id'], 'from': e['name'], 'to': name}, 'a typo in its name')
            note = ' '.join((fix.get('note') or '').split())
            if e.get('note') and small_fix(e['note'], note):
                made += add(store, 'note', {'id': e['id'], 'from': e['note'], 'to': note}, 'a typo in its note')
        if answer is not None:
            for e in batch:
                read[e['id']] = mark(e)
    return made


# ---------- links between motifs ----------
LINK_PROMPT = """Two motifs in our index of recurring rumor and narrative shapes, each with claims filed under it:

A. {a}

B. {b}

How are they related, judging by each motif's name, note and claims: what kind of story each one is? A claim can be \
filed under several motifs at once (one story can carry several shapes), so two motifs holding the same claim are not \
the same motif for that.
- "A is a kind of B": every A story is also a B story, a narrower version of it
- "B is a kind of A": the other way round
- "the same motif": two names for one kind of story
- "related": different kinds of story that are often told together or are close cousins
- "unrelated": a shared topic, person or word at most

reason: a sentence
relation: one of the five"""
RELATIONS = ["A is a kind of B", "B is a kind of A", "the same motif", "related", "unrelated"]
LINK_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                                "relation": {"type": "string", "enum": RELATIONS}},
               "required": ["reason", "relation"]}


def shown(e: dict, other: dict | None = None) -> str:
    """A motif for the model: its name, note and three of its claims, not ones it shares with `other` (shown the same
    claim under both, the model took them for the same motif)"""
    theirs = {c['claim'] for c in (other or {}).get('claims', [])}
    own = [c for c in e['claims'] if c['claim'] not in theirs][-3:]
    return mi.described(e) + ''.join(f'\n   - {c["claim"][:150]}' for c in own)


def vectors(entries: list[dict]) -> np.ndarray:
    from app.narratives import embed
    return embed([mi.described(e) + '. ' + '; '.join(c['claim'][:120] for c in e['claims'][-3:]) for e in entries])


def linked(index: dict, a: str, b: str) -> bool:
    ea, eb = index['entries'][a], index['entries'][b]
    return b in mi.parents_of(ea) or a in mi.parents_of(eb) or sorted([a, b]) in index.get('related', [])


def links(store: dict, index: dict, vecs: np.ndarray, entries: list[dict], deadline: float | None = None) -> int:
    import time
    ids = [e['id'] for e in entries]
    sims = vecs @ vecs.T
    pairs = {}
    for i in range(len(ids)):
        for j in np.argsort(-sims[i])[1:LINK_NEIGHBORS + 1]:
            if sims[i, j] >= LINK_FLOOR:
                pairs[tuple(sorted((i, int(j))))] = float(sims[i, j])
    # (no longer motifs that share claims, Oct 7: one claim often tells several shapes at once, one per layer of the
    # story, so motifs filed together co-occur without being related, as the person put it)
    marks = {e['id']: mark(e) for e in entries}
    asked = set()
    for p in store.values():
        a = p['args']
        x, y = a.get('a') or a.get('id'), a.get('b') or a.get('parent')
        if p['kind'] in ('parent', 'relate', 'merge', 'unrelate', 'unparent') or (  # unlinked by a person: never proposed back
                p['kind'] == 'unrelated' and a.get('marks') == sorted([marks.get(x, ''), marks.get(y, '')])):
            asked.add(json.dumps(sorted([x, y])))
    made = 0
    todo = [(s, i, j) for (i, j), s in pairs.items() if not linked(index, ids[i], ids[j])
            and json.dumps(sorted([ids[i], ids[j]])) not in asked]
    for s, i, j in sorted(todo, reverse=True)[:MAX_PAIRS]:
        if deadline and time.time() > deadline:
            raise Spent
        a, b = entries[i], entries[j]
        answer = llm.complete_json(LINK_PROMPT.format(a=shown(a, b), b=shown(b, a)), LINK_SCHEMA, max_tokens=500, model=MODEL)
        if not answer:
            continue
        rel, why = answer.get('relation'), answer.get('reason', '')
        if rel in RELATIONS[:2] and mi.genres_clash(a, b):
            pass  # a kind of stays within its genre
        elif rel == RELATIONS[0]:
            made += add(store, 'parent', {'id': a['id'], 'parent': b['id']}, why)
        elif rel == RELATIONS[1]:
            made += add(store, 'parent', {'id': b['id'], 'parent': a['id']}, why)
        elif rel == 'the same motif' and s >= MERGE_FLOOR and sorted([a['id'], b['id']]) not in index.get('not_same', []):
            small, big = sorted((a, b), key=lambda e: len(e['claims']))  # the smaller folds into the bigger
            made += add(store, 'merge', {'a': small['id'], 'b': big['id']}, why)
        elif rel in ('related', 'the same motif'):
            made += add(store, 'relate', {'a': a['id'], 'b': b['id']}, why)
        else:  # remembered with both motifs' marks: asked again only once either changes
            i2 = pid('unrelated', {'a': a['id'], 'b': b['id']})
            store[i2] = {'id': i2, 'kind': 'unrelated', 'args': {'a': a['id'], 'b': b['id'], 'marks': sorted([mark(a), mark(b)])},
                         'reason': why, 'model': MODEL, 'made': dt.now().isoformat(timespec='seconds'), 'status': 'none'}
    return made


# ---------- a review of the links already made ----------
def review(store: dict, index: dict, deadline: float | None = None) -> int:
    """Every related and kind-of link put to the same question as a new pair; one the model calls unrelated becomes a
    proposal to take it away. A link it keeps is remembered with both motifs' marks, so it's read again only once
    either changes; one a person decided on (kept or removed) never is"""
    import time
    entries = index['entries']
    live = {e['id']: e for e in mi.live(index)}
    links = [('unrelate', {'a': a, 'b': b}) for a, b in index.get('related', []) if a in live and b in live]
    links += [('unparent', {'id': e['id'], 'parent': p}) for e in live.values() for p in mi.parents_of(e) if p in live]
    made = 0
    for kind, args in links:
        x, y = (args.get('a') or args.get('id')), (args.get('b') or args.get('parent'))
        marks = sorted([mark(entries[x]), mark(entries[y])])
        if pid(kind, args) in store:  # proposed already (open or decided)
            continue
        ok = store.get(pid('link_ok', args))
        if ok and ok['args'].get('marks') == marks:
            continue
        if deadline and time.time() > deadline:
            raise Spent
        a, b = entries[x], entries[y]
        answer = llm.complete_json(LINK_PROMPT.format(a=shown(a, b), b=shown(b, a)), LINK_SCHEMA, max_tokens=500, model=MODEL)
        if not answer:
            continue
        if answer.get('relation') == 'unrelated':
            made += add(store, kind, args, answer.get('reason', ''))
        else:
            i = pid('link_ok', args)
            store[i] = {'id': i, 'kind': 'link_ok', 'args': {**args, 'marks': marks}, 'reason': answer.get('reason', ''),
                        'model': MODEL, 'made': dt.now().isoformat(timespec='seconds'), 'status': 'none'}
    return made


# ---------- groups ----------
GROUP_PROMPT = """A group of motifs a person made in our index of rumor and narrative shapes, "{group}":
{members}

Does this motif belong in the group, the way its members go together?
{motif}

reason: a sentence
belongs: true or false"""
GROUP_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                                 "belongs": {"type": "boolean"}}, "required": ["reason", "belongs"]}


def groups(store: dict, index: dict, vecs: np.ndarray, entries: list[dict], deadline: float | None = None) -> int:
    import time
    made = 0
    for gid, g in index.get('groups', {}).items():
        members = [i for i, e in enumerate(entries) if gid in mi.groups_of(e)]
        if len(members) < 3:
            continue
        center = vecs[members].mean(axis=0)
        sims = vecs @ center
        listing = '\n'.join(f'- {mi.described(entries[i])}' for i in members)
        for i in [int(i) for i in np.argsort(-sims) if int(i) not in members and sims[i] >= GROUP_FLOOR][:GROUP_CANDIDATES]:
            e = entries[i]
            no = store.get(pid('not_group', {'id': e['id'], 'group': gid}))
            if pid('group', {'id': e['id'], 'group': gid}) in store or (no and no['args'].get('mark') == mark(e)):
                continue
            if deadline and time.time() > deadline:
                raise Spent
            answer = llm.complete_json(GROUP_PROMPT.format(group=g['name'], members=listing, motif=shown(e)),
                                       GROUP_SCHEMA, max_tokens=400, model=MODEL)
            if not answer:
                continue
            if answer.get('belongs'):
                made += add(store, 'group', {'id': e['id'], 'group': gid}, answer.get('reason', ''))
            else:
                i2 = pid('not_group', {'id': e['id'], 'group': gid})
                store[i2] = {'id': i2, 'kind': 'not_group', 'args': {'id': e['id'], 'group': gid, 'mark': mark(e)},
                             'reason': answer.get('reason', ''), 'model': MODEL,
                             'made': dt.now().isoformat(timespec='seconds'), 'status': 'none'}
    return made


# ---------- best fit: the judge's score and the person's own decisions ----------
JUDGE_PROMPT = """You check suggestions for our index of recurring rumor and narrative shapes (motifs) before a person \
sees them. The person links two motifs when the link is plain and useful to someone browsing the index, and rejects \
links that only hold at a stretch.

A. {a}

B. {b}

The suggestion: {link}
The suggester's reason: {reason}
{examples}
How likely is the person to accept this link? A good link: {test}. A weak one: the two only share a topic, a \
mood, a cause and effect, or the same people or events.

reason: a sentence
score: 0 (surely rejected) to 10 (surely accepted)"""
JUDGE_TESTS = {'relate': 'the same kind of story told from another side, or a close cousin that is often told with it',
               'parent': 'every story of the narrower one is plainly also a story of the broader one'}
JUDGE_SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                                 "score": {"type": "integer", "minimum": 0, "maximum": 10}},
                "required": ["reason", "score"]}


def pair(p: dict) -> tuple[str, str]:
    a = p['args']
    return (a['a'], a['b']) if p['kind'] == 'relate' else (a['id'], a['parent'])


def _live_pair(p: dict, index: dict) -> bool:
    return all(i in index['entries'] and not index['entries'][i].get('merged_into') for i in pair(p))


def _examples(p: dict, decided: list[dict], index: dict) -> str:
    """Some of the person's decisions on this kind of link (never this one), as names and notes"""
    import random
    same = [d for d in decided if d['kind'] == p['kind'] and d['id'] != p['id']]
    rnd = random.Random(p['id'])
    rows = []
    for status in ('approved', 'rejected'):
        mine = [d for d in same if d['status'] == status]
        rows += rnd.sample(mine, min(JUDGE_EXAMPLES, len(mine)))
    if not rows:
        return ''
    rnd.shuffle(rows)
    short = lambda i: f'{index["entries"][i]["name"]} ({(index["entries"][i].get("note") or "no note")[:120]})'  # noqa: E731
    lines = []
    for d in rows:
        x, y = pair(d)
        link = f'{short(x)} — related to — {short(y)}' if d['kind'] == 'relate' else f'{short(x)} — a kind of — {short(y)}'
        lines.append(f'- {"ACCEPTED" if d["status"] == "approved" else "REJECTED"}: {link}')
    return "\nSome of the person's past decisions on links like this:\n" + '\n'.join(lines) + '\n'


def judge(store: dict, index: dict, deadline: float | None = None) -> int:
    """The judge's score on each kind-of and related proposal not scored yet: open ones first, then decided ones
    (more to train best fit on)"""
    import time
    decided = [p for p in store.values() if p['kind'] in JUDGED and p['status'] in ('approved', 'rejected') and _live_pair(p, index)]
    todo = [p for p in store.values() if p['kind'] in JUDGED and 'judge' not in p and _live_pair(p, index)
            and (p['status'] in ('approved', 'rejected') or still_holds(p, index))]
    made = 0
    for p in sorted(todo, key=lambda p: p['status'] != 'open'):
        if deadline and time.time() > deadline:
            raise Spent
        x, y = pair(p)
        a, b = index['entries'][x], index['entries'][y]
        name = lambda e: f'“{e["name"]}”'  # noqa: E731
        link = f'{name(a)} and {name(b)} are related' if p['kind'] == 'relate' else f'{name(a)} is a kind of {name(b)}'
        answer = llm.complete_json(JUDGE_PROMPT.format(a=shown(a, b), b=shown(b, a), link=link, reason=p.get('reason', ''),
                                                       examples=_examples(p, decided, index), test=JUDGE_TESTS[p['kind']]),
                                   JUDGE_SCHEMA, max_tokens=500, model=MODEL)
        if not answer or not isinstance(answer.get('score'), int):
            continue
        p['judge'] = {'score': answer['score'], 'reason': answer.get('reason', ''), 'model': MODEL}
        made += 1
        if made % 10 == 0:
            save(store)  # a run cut short keeps its scores
    return made


FIT_FACTS = ['descriptions alike', 'claims alike', 'claims shared', 'same group', 'same genre', 'groups apart',
             'a kind-of link', 'judge']


def fit_facts(ps: list[dict], index: dict) -> np.ndarray:
    """For each proposal, the facts best fit weighs (FIT_FACTS)"""
    from app.narratives import embed
    ids = sorted({i for p in ps for i in pair(p)})
    es = {i: index['entries'][i] for i in ids}
    dv = dict(zip(ids, embed([mi.described(es[i]) for i in ids])))
    cv = dict(zip(ids, embed(['; '.join(c['claim'][:150] for c in es[i]['claims'][-5:]) or es[i]['name'] for i in ids])))
    rows = []
    for p in ps:
        a, b = pair(p)
        ea, eb = es[a], es[b]
        ka, kb = ({mi.key(c['claim']) for c in e['claims']} for e in (ea, eb))
        ga, gb = set(mi.groups_of(ea)), set(mi.groups_of(eb))
        fa, fb = ((e.get('facets') or {}).get('genre') for e in (ea, eb))
        rows.append([float(dv[a] @ dv[b]), float(cv[a] @ cv[b]), np.log1p(len(ka & kb)), float(bool(ga & gb)),
                     float(bool(fa and fa == fb)), float(bool(ga and gb and not ga & gb)), float(p['kind'] == 'parent'),
                     p['judge']['score'] / 10])
    return np.array(rows)


def best_fit(store: dict, index: dict) -> dict | None:
    """Trains best fit on the person's decisions (scored by the judge) and gives each open kind-of and related
    proposal its chance of approval ('fit'); the fold's cut is kept in RUNS. None until FIT_MIN decisions"""
    from sklearn.linear_model import LogisticRegression
    scored = [p for p in store.values() if p['kind'] in JUDGED and 'judge' in p and _live_pair(p, index)]
    decided = [p for p in scored if p['status'] in ('approved', 'rejected')]
    todo = [p for p in scored if p['status'] == 'open' and still_holds(p, index)]
    if len(decided) < FIT_MIN or len({p['status'] for p in decided}) < 2:
        return None
    X = fit_facts(decided + todo, index)
    y = np.array([p['status'] == 'approved' for p in decided])
    mu, sd = X[:len(decided)].mean(0), X[:len(decided)].std(0) + 1e-9
    model = LogisticRegression(max_iter=1000).fit((X[:len(decided)] - mu) / sd, y)
    chance = model.predict_proba((X - mu) / sd)[:, 1]
    for p, c in zip(todo, chance[len(decided):]):
        p['fit'] = round(float(c), 3)
    cut = float(np.quantile(chance[:len(decided)][y], 1 - FIT_KEEP))
    info = {'cut': round(cut, 3), 'trained_on': len(decided), 'approved': int(y.sum()), 'at': dt.now().isoformat(timespec='seconds'),
            'weights': dict(zip(FIT_FACTS, [round(float(w), 2) for w in model.coef_[0]]))}
    runs = read_json(RUNS, {})
    runs['fit'] = info
    write_json(RUNS, runs)
    return info


def genre_clashes(store: dict, index: dict) -> int:
    """Kind-of links between motifs of two genres, made before the rule that a kind of stays within its genre: each
    proposed for removal (no model needed)"""
    made = 0
    for e in mi.live(index):
        for p in mi.parents_of(e):
            if p in index['entries'] and mi.genres_clash(e, index['entries'][p]):
                made += add(store, 'unparent', {'id': e['id'], 'parent': p},
                            f'{mi.genre_of(e)} and {mi.genre_of(index["entries"][p])}: a kind of stays within its genre')
    return made


def propose(kinds=('typos', 'links', 'review', 'groups', 'judge'), budget: float | None = None) -> dict:
    """One run: new proposals of each kind, saved as it goes. Returns how many of each, and 'finished': whether it
    got through everything before the budget (seconds) ran out"""
    import time
    deadline = time.time() + budget if budget else None
    index = mi.load()
    store, runs = load(), read_json(RUNS, {})
    entries = mi.live(index)
    counts = {'finished': False, 'genre clashes': genre_clashes(store, index)}
    try:
        if 'typos' in kinds:
            counts['typos'] = typos(store, index, runs, deadline)
        if {'links', 'groups'} & set(kinds):
            vecs = vectors(entries)
            if 'links' in kinds:
                counts['links'] = links(store, index, vecs, entries, deadline)
            if 'groups' in kinds:
                counts['groups'] = groups(store, index, vecs, entries, deadline)
        if 'review' in kinds:
            counts['review'] = review(store, index, deadline)
        if 'judge' in kinds:
            counts['judge'] = judge(store, index, deadline)
        counts['finished'] = True
    except Spent:
        pass
    finally:
        save(store)
        write_json(RUNS, runs)
    if 'judge' in kinds:  # best fit on whatever was scored, even in a run cut short
        try:
            counts['fit'] = best_fit(store, index)
            save(store)
        except Exception as e:  # noqa: BLE001 — sorting is a nicety; the proposals stand without it
            logger.warning("Best fit failed: %s", e)
    logger.info("Motif proposals: %s", counts)
    return counts


def nightly(budget: float = NIGHT_BUDGET):
    """Once a day, after the morning's report and its first filings: new proposals for what changed. A run cut short
    by its budget goes on in the next hour's run"""
    from datetime import date
    runs = read_json(RUNS, {})
    today = date.today().isoformat()
    if runs.get('done') == today:
        return
    if propose(budget=budget).get('finished'):
        runs = read_json(RUNS, {})
        runs['done'] = today
        write_json(RUNS, runs)
