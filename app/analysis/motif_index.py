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
{'next': 3, 'entries': {'M001': {...}}, 'claims': {claim key: [entry ids]}} (an empty list: filed, no motif kept).

This file is the index's store (load, save, the lock, batches) and its reading: lookups, queries and the small helpers
the rest share. Filing is in motif_filing.py, the verbs in motif_edit.py, the model's drafted notes in motif_notes.py,
all reached through here (see _MOVED at the end)."""
import contextlib
import functools
import json
import hashlib
import os
import re
import threading

import numpy as np

from app.utils import Config, get_logger, store
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

INDEX = os.path.join(Config.data, 'motif_index.sqlite')  # the index's database (motif_db.py), since Oct 21


def legacy() -> str | None:
    """The JSON file the index lived in until Oct 21, read and written in its place until it's moved in (migrate)"""
    return INDEX[:-len('.sqlite')] + '.json' if INDEX.endswith('.sqlite') else None


def _json_mode() -> bool:
    lg = legacy()
    return not os.path.exists(INDEX) and lg is not None and os.path.exists(lg)


def clean(name: str) -> str:
    """A motif name without stray CJK characters (Qwen sometimes drifts into Chinese mid-phrase) or end punctuation."""
    return re.sub(r'[\u3000-\u9fff\uff00-\uffef]+', '', name).strip().rstrip('.,;:')


def key(claim: str) -> str:
    return hashlib.sha1(claim.strip().lower().encode()).hexdigest()[:16]


def _read() -> dict:
    from app.analysis import motif_db
    if _json_mode():
        return read_json(legacy(), {'next': 1, 'entries': {}, 'claims': {}})
    return motif_db.read(INDEX)


def load() -> dict:
    if getattr(_batch, 'on', False):  # inside batched(): the batch's own copy, changed step by step
        if _batch.index is None:
            _batch.index = _read()
        return _batch.index
    return _read()


_snap = {'path': None, 'version': None, 'index': None}


def snapshot() -> dict:
    """The index as last saved, parsed once per save and shared: for reading only. The checker's views read the index
    several times a request (Oct 22: four reads of it in every workbench state, 0.14 of its 0.37 s); this reads it
    once a save. Never change what it gives: load() gives a copy of one's own to change and save"""
    if getattr(_batch, 'on', False):  # inside a batch: the batch's own copy, as load() gives
        return load()
    v = version()  # the stamp first: a save landing between the two is read again next time, never missed
    if _snap['index'] is None or _snap['path'] != INDEX or _snap['version'] != v:
        _snap.update(path=INDEX, version=v, index=_read())
    return _snap['index']


def save(index: dict):
    drop_dangling(index)
    drop_related_resting(index)
    drop_loose_notes(index)
    if getattr(_batch, 'on', False):  # written once, when the batch ends
        _batch.index, _batch.dirty = index, True
        return
    _write(index)


def _write(index: dict):
    """Only the rows that changed, each logged with its old value (motif_db.py); before the move, the whole JSON file
    and a copy of it in curation.sqlite, as it was until Oct 21"""
    from app.analysis import motif_db
    if _json_mode():
        write_json(legacy(), index, indent=1)
        from app.analysis import curation_db
        with open(legacy()) as f:
            curation_db.record_version(f.read())
        return
    motif_db.write(INDEX, index)


def version() -> int | float:
    """Changes whenever the index does: the last save's number (a cache's stamp)"""
    from app.analysis import motif_db
    if _json_mode():
        return os.path.getmtime(legacy())
    return motif_db.txn(INDEX)


def export_text(index: dict | None = None) -> str:
    """The index as JSON text: what a saved state (curation_db.checkpoint) keeps"""
    return json.dumps(index if index is not None else load(), ensure_ascii=False, indent=1)


def revert_to(txn: int):
    """The index put back as it was after save `txn` (the checker's undo), under the lock, as a save of its own"""
    from app.analysis import motif_db
    with locked():
        motif_db.revert(INDEX, txn)


def load_from(path: str) -> dict:
    """Another copy of the index, by its path: a database, or a JSON file from before the move"""
    from app.analysis import motif_db
    if path.endswith('.json') and os.path.exists(path):
        return read_json(path, {'next': 1, 'entries': {}, 'claims': {}})
    if not os.path.exists(path) and path.endswith('.sqlite') and os.path.exists(path[:-len('.sqlite')] + '.json'):
        return read_json(path[:-len('.sqlite')] + '.json', {'next': 1, 'entries': {}, 'claims': {}})
    return motif_db.read(path)


def migrate() -> dict:
    """Move the index from its JSON file into the database, under the lock: run once, when every process is on the
    new code (see motif_db.py)"""
    from app.analysis import motif_db
    lg = legacy()
    if not lg or not os.path.exists(lg):
        raise ValueError('no JSON index to move')
    with locked():
        return motif_db.migrate(lg, INDEX)


def locked():
    """One writer at a time: the hourly filing and the organizer and motif check pages each read, change and save the
    whole index, so without this an edit made while a run was filing was lost when the run saved. Inside this thread's
    batch the batch holds it already: taking it again (a split in a batch, claim_organizer.apply_split) waited on itself
    forever, and every write to the checker after it hung (Oct 19).

    Hold it only to apply a change: ask the models first, on an unlocked read, then take the lock, read again and
    apply what still holds (motif_filing.file_claims, watch_list.refile, motif_notes). Until Oct 21 the filing held it
    through each claim's model calls and the checker waited on every click while a run filed. Fable's review proposed
    making the checker the only writer, with the runs posting their changes to it; that was not done, because
    experiments run the same filing code against their own copy of the data (MAUDLIN_DATA) and would have posted into
    production's checker.

    The lock is the database's (INDEX + '.lock'). Until the index is moved in (migrate), the JSON file's lock is taken
    too, after it: code from before Oct 21 takes only that one, and a worker finishing a cycle on it must not write
    beside the new code."""
    if getattr(_batch, 'on', False):
        return contextlib.nullcontext()
    return _both_locks()


@contextlib.contextmanager
def _both_locks():
    with store.locked(INDEX):
        lg = legacy()
        if lg and os.path.exists(lg):
            with store.locked(lg):
                yield
        else:
            yield


# A batch of changes (the checker's batch: a page of sure claims passed, a multi-select drag) saved once at the end
# (Oct 19: each of a 29-filing pass saved the whole 1.7 MB index and kept a version of it, ten seconds idle and over a
# minute while the hourly run worked; the person pressed again, not knowing it had registered). Per thread: the
# checker serves requests on threads
_batch = threading.local()


@contextlib.contextmanager
def batched():
    """Every load and save inside the block works on one copy of the index, under the lock, written (and kept as one
    version) when the block ends, also if a step fails: the steps before it stay done, as they did step by step"""
    if getattr(_batch, 'on', False):
        yield
        return
    with locked():
        _batch.on, _batch.index, _batch.dirty = True, None, False
        try:
            yield
        finally:
            index, dirty = _batch.index, _batch.dirty
            _batch.on, _batch.index, _batch.dirty = False, None, False
            if dirty:
                _write(index)


def exclusive(fn):
    @functools.wraps(fn)
    def run(*args, **kwargs):
        if getattr(_batch, 'on', False):  # the batch holds the lock already (it isn't reentrant)
            return fn(*args, **kwargs)
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


STORY_FIELDS = ('story', 'story_tie')  # carried onto the filing when the claim's source ties it to a story


# Stories (Oct 12, the person's decision on Straight news): a filing keeps the story its claim was told about, so
# "which motifs is story S told in, in time order" is a join, with the plain report as its baseline. A story id is a
# row of the site database's story table (app/models.Story): one news event as covered across outlets, kept across the
# hourly runs (each run's clusters continue the story that holds most of their headlines, and a story back on the front
# pages under new headlines gets its old id back: app/analysis/stories.sync_stories). An id lasts unless the story is
# folded into another (stories.merge_stories, by hand or a return the model missed); the gone id is kept in
# story_merges.json and followed here. Labels get reworded, so ties are by id. A story isn't a saga: sagas are loose
# clusters of stories by design (Story.saga_id). A narrative's tie is the model's, to one of the stories seen last
# when the report was made ('story_tie': 'same event' or 'same issue', app/narratives.story_link); a fact-check's is
# the one its card showed (factchecks.stories_of). The Focus Group's and the shows' claims carry none


def watched(index: dict) -> set[str]:
    """The motifs a person marked as watch lists (set_watch): a sink for plain reports, Straight news first of all,
    whose claims are watched and filed again (watch_list.py)"""
    return {e['id'] for e in live(index) if e.get('watch')}


def story_of_group(g: dict) -> dict:
    """A narrative report group's story tie as claim fields ({} when it has none or no id)"""
    st = g.get('story') or {}
    if st.get('id') is None:
        return {}
    return {'story': int(st['id']), **({'story_tie': st['relation']} if st.get('relation') else {})}


def story_motifs(story_id: int, index: dict | None = None) -> list[dict]:
    """Which motifs a story is told in, in time order: a row per filing of a claim tied to the story (or to a story
    since merged into it), {'date', 'claim', 'source', 'story_tie', 'motif', 'name', 'checked', 'plain'}; 'plain' marks
    the plain report (filed in a watched motif, Straight news, or with no motif: 'motif' None, from the watch list,
    which keeps the words the index drops), the baseline the tellings are read against."""
    from app.analysis.stories import merges
    gone = merges()
    target = gone.get(int(story_id), int(story_id))
    index = index if index is not None else load()
    plain = watched(index)
    rows = []
    for e in live(index):
        for c in e['claims']:
            if c.get('story') is not None and gone.get(int(c['story']), int(c['story'])) == target:
                rows.append({'date': c.get('date', ''), 'claim': c['claim'], 'source': c.get('source', ''),
                             'story_tie': c.get('story_tie'), 'motif': e['id'], 'name': e['name'],
                             'checked': c.get('checked'), 'plain': e['id'] in plain})
    from app.analysis import watch_list  # claims with no motif: their words and story are kept there
    for w in watch_list.load()['claims'].values():
        if w.get('story') is not None and gone.get(int(w['story']), int(w['story'])) == target \
                and index['claims'].get(w['key']) == []:
            rows.append({'date': w.get('date', ''), 'claim': w['claim'], 'source': w.get('source', ''),
                         'story_tie': w.get('story_tie'), 'motif': None, 'name': None, 'checked': None, 'plain': True})
    return sorted(rows, key=lambda r: (r['date'], r['claim'], r['motif'] or ''))

# Curation, from the organizer on the label-check page (scripts/validate.py). A curated name is kept as given; a
# merged entry points to the one it joined, so its number still resolves; a deleted entry's claims are marked
# dropped (None), so the nightly filing leaves them out rather than filing them again.
SUGGEST = 0.72  # entry names at least this alike are suggested as merges
SUGGESTED = 15


def held(index: dict | None = None) -> dict:
    """The claims on hold: claim key -> {'claim', 'at'}"""
    return (index if index is not None else load()).get('held', {})


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
    for e in sorted(live(snapshot()), key=lambda e: (-len(e['claims']), e['id'])):
        for c in e['claims']:
            if not c.get('checked'):
                out.append({'id': e['id'], 'name': e['name'], 'size': len(e['claims']), 'claim': c['claim'],
                            'source': c.get('source', ''), 'others': [x['claim'] for x in e['claims'] if x is not c][:2]})
    return out[:limit] if limit else out


def attested(entry: dict) -> bool:
    """Told on two occasions or more (motif_told.py); placed, not yet attested, otherwise. Before the first count, a
    motif with two kept claims or more counts as attested."""
    t = entry.get('told')
    return t['events'] >= 2 if t else sum(c.get('checked') == 'yes' for c in entry.get('claims', [])) >= 2


# Groups: a person's own chapters over the motifs (as Thompson grouped his into chapters), made on the motif board.
# Kept in the index: 'groups' (id -> name) and each entry's 'groups', a list: a motif can be in several (Oct 6: "Owned
# politician" is a kind of Money in politics and also a Politician archetype). Entries saved before then have a single
# 'group', read as a list of one.


def groups_of(entry: dict) -> list[str]:
    return list(entry.get('groups') or ([entry['group']] if entry.get('group') else []))


def _set_groups(entry: dict, gids: list[str]):
    entry.pop('group', None)
    if gids:
        entry['groups'] = list(dict.fromkeys(gids))
    else:
        entry.pop('groups', None)
    drafted = [g for g in (entry.get('by_model') or {}).get('groups', []) if g in (gids or [])]
    _drafts(entry, groups=drafted)


# Drafts at birth (Oct 8, the person: "when the model generates new motifs can it also try to generate notes and a
# genre and groups?"): a motif the model makes gets the model's note, genre and groups straight away, the genre and
# groups marked as the model's in entry['by_model'] ({'genre': value, 'groups': [ids]}; the note by note_by, as before).
# Marking the motif done makes them the person's; so does setting its genre or putting it in a group by hand. Until
# then nothing learns from them: genre examples, group centers and the group signal read the person's own only.

def _drafts(entry: dict, **fields):
    """Set (or with a falsy value, drop) fields of the model's drafts; drops by_model once empty"""
    d = dict(entry.get('by_model') or {})
    for k, v in fields.items():
        if v:
            d[k] = v
        else:
            d.pop(k, None)
    if d:
        entry['by_model'] = d
    else:
        entry.pop('by_model', None)


def person_genre(entry: dict) -> str | None:
    """Its genre, unless the model's draft"""
    g = genre_of(entry)
    return None if g and (entry.get('by_model') or {}).get('genre') == g else g


def person_groups(entry: dict) -> list[str]:
    """Its groups, but those the model drafted"""
    drafted = set((entry.get('by_model') or {}).get('groups', []))
    return [g for g in groups_of(entry) if g not in drafted]


# Facets: ways of sorting motifs that cut across the rests-on links, one value per motif in each. Genre first, its
# starting values the genres the narrative labeler uses; a person adds more. (Later, perhaps: Barkun's conspiracy scope,
# a frame from the Media Frames codebook.)
# A motif's genre: only the ones the person makes (the 13 starting ones were dropped on their word, Oct 7)
FACETS = {'genre': []}


def facet_values(index: dict | None = None) -> dict[str, list[str]]:
    """Each facet's values: the starting ones, the ones a person added, and any in use"""
    index = index if index is not None else load()
    out = {}
    for facet, start in FACETS.items():
        used = [e.get('facets', {}).get(facet) for e in live(index)]
        hidden = set(index.get('facet_hidden', {}).get(facet, []))  # starting values a person renamed or removed
        out[facet] = sorted(dict.fromkeys([v for v in start if v not in hidden] + index.get('facet_values', {}).get(facet, [])
                                          + [u for u in used if u]), key=str.lower)  # A to Z
    return out


def facet_notes(index: dict | None = None) -> dict[str, dict[str, str]]:
    """Each facet value's description (a genre's: what kind of thing its motifs are), where the person wrote one"""
    return (index if index is not None else load()).get('facet_notes', {})


def board(index: dict | None = None) -> dict:
    """Everything the motif board shows: groups, and every live motif with its claims"""
    index = index if index is not None else load()
    entries = [{'id': e['id'], 'name': e['name'], 'group': (groups_of(e) or [None])[0], 'groups': groups_of(e),
                'curated': bool(e.get('curated')),
                'done': is_done(e), 'note': e.get('note', ''), 'note_by': e.get('note_by', 'person' if e.get('note') else ''),
                'parents': [p for p in parents_of(e) if p in index['entries'] and not index['entries'][p].get('merged_into')],
                'related': sorted({x for p in index.get('related', []) if e['id'] in p for x in p
                                   if x != e['id'] and x in index['entries'] and not index['entries'][x].get('merged_into')}),
                'related_notes': {x: why for pair, why in index.get('related_notes', {}).items() if e['id'] in pair.split('|')
                                  for x in pair.split('|') if x != e['id']},
                'not_this': e.get('not_this', ''), 'told': e.get('told'), 'attested': attested(e),
                'first_seen': e.get('first_seen', ''), 'last_seen': e.get('last_seen', ''),
                'facets': e.get('facets', {}), 'by_model': e.get('by_model', {}),
                # In a motif marked done, the claims that came in since (the ones to look at)
                'claims': [{'claim': c['claim'], 'source': c.get('source', ''), 'ref': c.get('ref', ''),
                            'id': key(c['claim'])[:6],  # shown as #3f9a2b, to name a claim in a screenshot or a search
                            'checked': c.get('checked'), 'new': 'done' in e and not seen(e, c),
                            **({'carrying': c['carrying']} if c.get('carrying') else {}),
                            **({'variants': [v['claim'] for v in c['variants']]} if c.get('variants') else {})}
                           for c in e['claims']]}
               for e in live(index)]
    groups = sorted(index.get('groups', {}).values(), key=lambda g: g['name'].lower())  # A to Z wherever they're listed
    return {'groups': groups, 'entries': entries, 'facets': facet_values(index), 'facet_notes': facet_notes(index)}


def done_by_note(entry: dict) -> bool:
    """A motif a person made (or renamed) with a note of theirs is done: writing the note was the looking over (Oct 7:
    'if I create a motif and give it a note it's done'). Marks it done, with the claims it holds now, unless it's done
    already or they unmarked it; True if it did."""
    if 'done' in entry or entry.get('not_done') or not entry.get('curated') or not entry.get('note') \
            or entry.get('note_by') in DRAFTS:
        return False
    entry['done'] = sorted(key(c['claim']) for c in entry['claims'])
    return True


def seen(entry: dict, claim: dict) -> bool:
    """Whether a person has seen a claim in this motif: it was there when they marked the motif done, or they checked
    it ✓ or filed it by hand since (until Oct 7 only the first counted, so a claim checked after the motif was done
    still showed as new and stayed off the site)"""
    return key(claim['claim']) in set(entry.get('done') or []) or claim.get('checked') == 'yes'


def is_done(entry: dict) -> str | None:
    """'done', 'new' (marked done, then a claim came in that nobody has checked), or None"""
    if 'done' not in entry:
        return None
    return 'done' if all(seen(entry, c) for c in entry['claims']) else 'new'


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


_VECS: dict = {}  # claim text -> its mxbai vector, kept in the process: the checker's similar claims
TEXT_DIM = 1024  # mxbai's width; the static fallback's is narrower, and never kept


def _vectors(texts: list[str]):
    """The texts' vectors, from memory where known (Oct 22: similar claims read every claim's vector from the 3.7 GB
    cache on each call, 0.4 s, 3.5 s with the GPU busy; now only a new claim is asked for)"""
    import numpy as np
    from app.narratives import embed
    missing = [t for t in dict.fromkeys(texts) if t not in _VECS]
    if missing:
        v = embed(missing)
        if v.shape[1] != TEXT_DIM:  # Ollama down: the static model for all of them, this once, kept nowhere
            return embed(texts)
        _VECS.update(zip(missing, v))
    return np.vstack([_VECS[t] for t in texts])


def similar_claims(claim: str, n: int = 8) -> list[dict]:
    """The claims closest in meaning to one claim (cosine similarity of their embeddings), filed or not: to spot the
    same claim told another way (same_claim) or a neighbor worth filing with it. Its own wordings are left out."""
    index = snapshot()
    mine = originals(claim, index) | {claim}
    for e in entries_of(index, claim):
        for c in e['claims']:
            if key(c['claim']) == key(claim):
                mine |= {v.get('claim', '') for v in c.get('variants', [])}
    items = [c for c in searchable_claims() if c['claim'] not in mine and key(c['claim']) != key(claim)]
    if not items:
        return []
    v = _vectors([claim] + [c['claim'] for c in items])
    for c, s in zip(items, v[1:] @ v[0]):
        c['score'] = round(float(s), 3)
    return sorted(items, key=lambda c: -c['score'])[:n]


# Rests on: a motif can rest on others, only making sense given them: a kind of them ('Pedophile cabal' rests on 'Elite
# cabal'), or a case, argument or figure that tells them ('Radical left' rests on 'Overton window'; an Argument on a
# Theory). A person's links between motifs, finer than groups, kept as each entry's 'parents' (named 'kind of' until
# Oct 8, and held within one genre from Oct 7; the person then found that the links that crossed genres, an argument
# resting on a theory, were the same link). Several, as in a thesaurus, not a tree; never a loop.

def parents_of(entry: dict) -> list[str]:
    """Its parents (entries saved with a single 'parent' before Oct 5 afternoon read as a list of one)"""
    return list(entry.get('parents') or ([entry['parent']] if entry.get('parent') else []))


def resting(entries: dict, a: str, b: str) -> bool:
    """One of the two rests on the other"""
    return b in parents_of(entries.get(a, {})) or a in parents_of(entries.get(b, {}))


def drop_related_resting(index: dict) -> int:
    """A rests-on link says they belong together: no related link besides it (the person, Oct 8: 'every rests on
    shouldn't need a relate'). Kept so at every save, whatever made the pair (a new rests-on, a merge, a proposal)"""
    entries = index.get('entries', {})
    links = index.get('related', [])
    kept = [p for p in links if not resting(entries, p[0], p[1])]
    if len(kept) != len(links):
        index['related'] = kept
    return len(links) - len(kept)


def drop_dangling(index: dict) -> int:
    """Rests-on and related links to a motif that's gone (deleted, or emptied by a move) go with it: until Oct 9 they
    stayed, and three motifs rested on a deleted M402 that the checker couldn't take them off"""
    entries = index.get('entries', {})
    gone = 0
    for e in entries.values():
        parents = parents_of(e)
        kept = [p for p in parents if p in entries]
        if len(kept) != len(parents):
            gone += len(parents) - len(kept)
            e['parents'] = kept
            e.pop('parent', None)
    links = index.get('related', [])
    kept_links = [p for p in links if p[0] in entries and p[1] in entries]
    if len(kept_links) != len(links):
        gone += len(links) - len(kept_links)
        index['related'] = kept_links
    return gone


def drop_loose_notes(index: dict) -> int:
    """A related link's reason goes when the link does (taken away, dropped for a rests-on link, or dangling)"""
    notes = index.get('related_notes')
    if not notes:
        return 0
    links = {'|'.join(p) for p in index.get('related', [])}
    loose = [pair for pair in notes if pair not in links]
    for pair in loose:
        del notes[pair]
    return len(loose)


def related_note(index: dict, a: str, b: str) -> str:
    """The person's reason for a related link, if they gave one"""
    return index.get('related_notes', {}).get('|'.join(sorted([a, b])), '')


def genre_of(entry: dict) -> str | None:
    return (entry.get('facets') or {}).get('genre') or None


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
    from app.narratives import latest_report, withheld
    index = snapshot()
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
    from app.analysis import show_claims
    for c in show_claims.claims():
        text = corrected(c['claim'], index)
        out.setdefault(key(text), {'claim': text, 'source': c['source'], 'ref': c['ref'], 'motifs': []})
    return list(out.values())


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
    settled = {frozenset(p) for p in index.get('not_same', [])}  # kept apart, related or resting: decided already
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
        open_ = lambda m: m['id'] != e['id'] and frozenset([e['id'], m['id']]) not in settled  # noqa: E731, B023 - used in this iteration only
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


def not_this(entry: dict) -> str:
    """The line the models read after a motif's description: what it isn't, or nothing"""
    return f"\n   Not this: {entry['not_this']}" if entry.get('not_this') else ''


def phrases_in(text) -> list[str]:
    """A person's carrying words as a list: one phrase per ';' or line, spaces tidied, each once"""
    parts = text if isinstance(text, list) else str(text or '').replace('\n', ';').split(';')
    return list(dict.fromkeys(p for p in (' '.join(str(x).split()).strip(' "“”') for x in parts) if p))


def carrying(entry: dict) -> list[tuple[str, int]]:
    """A motif's phrase dictionary so far: the carrying words of its filings, each with how many filings carry it,
    most first (case aside, the first spelling kept)"""
    seen, count = {}, {}
    for c in entry.get('claims', []):
        for p in c.get('carrying') or []:
            k = p.lower()
            seen.setdefault(k, p)
            count[k] = count.get(k, 0) + 1
    return sorted(((seen[k], n) for k, n in count.items()), key=lambda x: (-x[1], x[0].lower()))


DRAFTS = ('model', 'claude')  # notes drafted, not yet kept: the local model's, or the Oct 5 one-off backfill by Claude


def public(entry: dict) -> bool:
    """Whether the site may show a motif: only ones a person has verified, by looking over its claims and marking it
    done (the board's and the workbench's ✓ done). The model's motifs stay in the index, and in the checker, until then."""
    return 'done' in entry and not entry.get('merged_into')  # its list of seen claims may be empty: a seed marked done


def public_claims(entry: dict) -> list[dict]:
    """The claims of a verified motif the site shows: those it held when a person marked it done, and those a person
    has checked ✓ or filed by hand since. The model's filings since wait for a check or for done again."""
    return [c for c in entry['claims'] if seen(entry, c)]


def public_note(entry: dict) -> str:
    """The note the site shows: a person's (written or kept), never a draft"""
    return entry.get('note', '') if entry.get('note') and entry.get('note_by') not in DRAFTS else ''


# The index's filing, its verbs and its note drafting live in modules of their own (Oct 21, Fable's architecture
# review: this file had grown to 2,050 lines). They are reached through here as before (mi.file_claims, mi.add,
# mi.gloss), looked up when first asked for, so those modules can import this one without a cycle. A test stands in
# for one where it lives (motif_filing.closest), since the moved code calls its neighbours directly.
_MOVED = {
    'motif_filing': (
        'CANDIDATES', 'FILING_LOG', 'JUDGE_MODEL', 'LINK_FIELDS', 'MATCH_FLOOR', 'MATCH_PROMPT', 'MAX_NEW',
        'MAX_WORDS', 'METRICS', 'MODEL', 'NAME_PROMPT', 'NAME_RULES', 'NAME_SCHEMA', 'NEW_PROMPT', 'REUSE_PROMPT',
        'SHORTLIST_LOG', 'SHOWN', 'SHOWN_FLOOR', 'Shortlister', 'backfill_stories', 'closest', 'file_claims', 'fits',
        'fits_name', 'log_shortlist', 'match', 'metrics', 'metrics_history', 'model_days', 'name_claim', 'nightly',
        'record', 'report_stories', 'same_name', 'snapshot_metrics', 'sure_share',
    ),
    'motif_edit': (
        '_add', 'add', 'add_facet_value', 'also_file', 'check', 'correct_claim', 'delete', 'facet_note',
        'facet_remove', 'facet_rename', 'file_by_hand', 'group_add', 'group_assign', 'group_delete', 'group_member',
        'group_note', 'group_rename', 'hold', 'keep_note', 'mark_done', 'merge', 'move', 'no_motif', 'not_same',
        'reject', 'relate', 'rename', 'reset_done', 'same_claim', 'set_carrying', 'set_facet', 'set_fits',
        'set_not_this', 'set_note', 'set_parent', 'set_told', 'set_watch', 'stands_alone', 'story_for', 'unfile',
        'withdraw',
    ),
    'motif_notes': (
        'GLOSS_CLAIMS', 'GLOSS_MIN', 'GLOSS_MODEL', 'GLOSS_PROMPT', 'GLOSS_SCHEMA', 'VERDICT_WORDS', 'draft_missing',
        'gloss', 'gloss_missing', 'names_in', 'needs_drafts', 'needs_gloss',
    ),
}
_HOME = {name: module for module, names in _MOVED.items() for name in names}


def __getattr__(name: str):
    home = _HOME.get(name)
    if home is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    import importlib
    return getattr(importlib.import_module(f'app.analysis.{home}'), name)
