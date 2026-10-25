"""The motif index's verbs (split from motif_index.py on Oct 21, Fable's architecture review): every change a person
makes in the checker or asks for through the MCP server (rename, merge, move, check, groups, genres, rests-on and
related links, notes, splits' bookkeeping), each under the index's lock (motif_index.exclusive). Reached as before
through motif_index (mi.add, mi.merge, mi.check)."""
import os
from datetime import datetime as dt


from app.utils import get_logger
from app.utils.store import read_json
from app.analysis import motif_index as mi

logger = get_logger(__name__)


@mi.exclusive
def set_watch(eid: str, on: bool = True):
    """A person marks a motif as a watch list, or not: its claims are plain reports, not tellings of a shape; each
    is watched and filed again as the index grows (watch_list.py), and a story's filings in it are its baseline
    (story_motifs). Straight news, by the person's decision of Oct 12: a sink and a watch list, not a Perennial"""
    index = mi.load()
    entry = index['entries'][eid]
    if entry.get('merged_into'):
        raise ValueError(f'{eid} is gone')
    if on:
        entry['watch'] = True
    else:
        entry.pop('watch', None)
    mi.save(index)


@mi.exclusive
def rename(eid: str, name: str):
    index = mi.load()
    index['entries'][eid].update(name=mi.clean(name), curated=True)
    mi.done_by_note(index['entries'][eid])
    mi.save(index)


def _add(name: str) -> str:
    index = mi.load()
    eid = f"M{index['next']:03d}"
    index['next'] += 1
    index['entries'][eid] = {'id': eid, 'name': mi.clean(name), 'curated': True, 'claims': [], 'phrases': [],
                             'first_seen': dt.now().strftime('%Y-%m-%d')}
    mi.save(index)
    return eid


@mi.exclusive
def add(name: str) -> str:
    return _add(name)


@mi.exclusive
def merge(source: str, target: str):
    """Fold `source` into `target`: its claims and phrases move over (a claim in both counts once), and its number
    points to `target`. Everything else it had comes along too (Oct 7; until then its broader motifs, groups, genre,
    note and 'not the same' verdicts were lost): its related links, what rests on it and what it rests on, its groups, its
    genre and note where the target has none, the claims a person saw when marking it done, and 'not the same'
    verdicts."""
    index = mi.load()
    if source == target:
        return
    src, dst = index['entries'][source], index['entries'][target]
    # what it rests on, unless that would make the target rest on itself or on something resting on it
    below = {target}
    while True:
        more = {e['id'] for e in index['entries'].values() if set(mi.parents_of(e)) & below} - below
        if not more:
            break
        below |= more
    ups = [p for p in mi.parents_of(dst) + mi.parents_of(src) if p != source and p not in below]
    if ups or 'parents' in dst or 'parent' in dst:
        dst.pop('parent', None)
        dst['parents'] = list(dict.fromkeys(ups))
    mi._set_groups(dst, list(dict.fromkeys(mi.groups_of(dst) + mi.person_groups(src))))
    for k, v in (src.get('facets') or {}).items():
        if not (k == 'genre' and mi.person_genre(src) is None):  # the model's draft stays behind
            dst.setdefault('facets', {}).setdefault(k, v)
    if src.get('note') and not dst.get('note'):
        dst['note'], dst['note_by'] = src['note'], src.get('note_by', 'person')
    if 'done' in src and 'done' in dst:  # both looked over: what was seen in either stays seen
        dst['done'] = list(dict.fromkeys(dst['done'] + src['done']))
    if src.get('watch'):  # a watched motif's claims stay watched where they go (Charybdis, the person's yes, Oct 13)
        dst['watch'] = True
    if src.get('not_this') and not dst.get('not_this'):
        dst['not_this'] = src['not_this']
    index['not_same'] = [p for p in (sorted([target if x == source else x for x in p]) for p in index.get('not_same', []))
                         if p[0] != p[1]]
    index['not_same'] = [p for i, p in enumerate(index['not_same']) if p not in index['not_same'][:i]]
    have = {mi.key(c['claim']) for c in dst['claims']}
    dst['claims'] += [c for c in src['claims'] if mi.key(c['claim']) not in have]
    dst['phrases'] = (dst.get('phrases', []) + src.get('phrases', []))[-20:]
    dst['first_seen'] = min(filter(None, [dst.get('first_seen'), src.get('first_seen')]), default=None)
    dst['last_seen'] = max(filter(None, [dst.get('last_seen'), src.get('last_seen')]), default=None)
    src.update(claims=[], merged_into=target)
    index['related'] = [sorted([target if x == source else x for x in p]) for p in index.get('related', [])]
    index['related'] = [p for i, p in enumerate(index['related']) if p[0] != p[1] and p not in index['related'][:i]]
    notes = {}  # the reasons for its related links come along; the target's own win
    for pair, why in index.get('related_notes', {}).items():
        a, b = sorted(target if x == source else x for x in pair.split('|'))
        if a != b and (f'{a}|{b}' not in notes or source not in pair):
            notes[f'{a}|{b}'] = why
    if notes or 'related_notes' in index:
        index['related_notes'] = notes
    for e in index['entries'].values():  # what rested on it rests on the motif it joined
        if source in mi.parents_of(e):
            e['parents'] = [p for p in dict.fromkeys(target if p == source else p for p in mi.parents_of(e)) if p != e['id']]
            e.pop('parent', None)
    for k in index['claims']:
        ids = [target if i == source else i for i in mi._ids(index, k)]
        index['claims'][k] = list(dict.fromkeys(ids))
    mi.save(index)


@mi.exclusive
def delete(eid: str):
    """Drop an entry: its claims keep their other motifs, and aren't filed again."""
    index = mi.load()
    for k in index['claims']:
        index['claims'][k] = [i for i in mi._ids(index, k) if i != eid]
    del index['entries'][eid]
    mi.save(index)


# A filing's fields that belong to its motif, not to the claim: left behind when the claim is copied or moved to another
# motif (Oct 25: a claim copied out of Words mean things kept its 0.22 there, so the model "doubted" it in its new motif)
PER_MOTIF = ('checked', 'fit', 'fit_model', 'rechecked', 'carrying', 'refiled')


def _for_motif(rec: dict) -> dict:
    """A filing as it goes to another motif by a person's hand: its motif's own fields dropped, checked"""
    return {**{k: v for k, v in rec.items() if k not in PER_MOTIF}, 'checked': 'yes'}


@mi.exclusive
def move(claim: str, source: str, target: str):
    """Move one claim out of `source` into another entry (or a new one, target 'new')."""
    if target == 'new':
        target = _add(claim[:80])  # already holding the lock
    index = mi.load()
    k = mi.key(claim)
    entry = index['entries'][source]
    moved = [c for c in entry['claims'] if mi.key(c['claim']) == k]
    entry['claims'] = [c for c in entry['claims'] if mi.key(c['claim']) != k]
    entry.setdefault('not_claims', []).append(k)  # moved out by hand: it isn't this motif
    if not any(mi.key(c['claim']) == k for c in index['entries'][target]['claims']):  # moved there by a person: checked
        index['entries'][target]['claims'] += [_for_motif(c) for c in moved]
    index['claims'][k] = list(dict.fromkeys([target if i == source else i for i in mi._ids(index, k)] + [target]))
    if not entry['claims'] and not entry.get('curated'):  # emptied: a motif the model made goes; one a person made stays
        del index['entries'][source]
    mi.save(index)


@mi.exclusive
def hold(claim: str, on: bool = True):
    """A claim put on hold, or taken off it (Oct 18, the person: "a thing to mark a post 'hold' because if i uncheck it
    it will keep reappearing. Basically I want to examine the claim further later"). A held claim leaves the checker's
    queues (🎯 claims to judge, ✅ sure, 🚫 misfits) for its own ⏸ held tab, its filings still waiting, until the person
    takes it off hold or decides them. Nothing about its filings changes: a hold is no verdict"""
    index = mi.load()
    k = mi.key(claim)
    if on:
        if k not in index['claims']:
            raise ValueError('no such claim in the index')
        index.setdefault('held', {})[k] = {'claim': claim, 'at': dt.now().isoformat(timespec='seconds')}
    elif k in index.get('held', {}):
        index['held'].pop(k)
    mi.save(index)


@mi.exclusive
def not_same(a: str, b: str):
    """Remember that two entries aren't the same motif, so they're not suggested again."""
    index = mi.load()
    index.setdefault('not_same', []).append(sorted([a, b]))
    mi.save(index)


@mi.exclusive
def set_fits(fits: dict, model_at: str):
    """Each filing's fit, (claim key, motif id) -> the chance the person keeps it (filing_confidence.py), kept on the
    filing with the model that gave it"""
    index = mi.load()
    for e in index['entries'].values():
        for c in e.get('claims', []):
            f = fits.get((mi.key(c['claim']), e['id']))
            if f is not None:
                c['fit'], c['fit_model'] = f, model_at
    mi.save(index)


@mi.exclusive
def set_told(told: dict):
    """Each motif's occasions, worked out by motif_told.py from its kept claims"""
    index = mi.load()
    for eid, t in told.items():
        if eid in index['entries']:
            index['entries'][eid]['told'] = t
    mi.save(index)


@mi.exclusive
def check(claim: str, eid: str, answer: str):
    """A person's answer to 'is this claim an instance of this motif?', applied at once. Yes or not sure is noted on
    the filing. No takes the claim out of the motif and keeps it out; a motif the model made left with no claims goes
    (one a person named stays). A claim left with no motif stays without one: not every claim tells a recurring story,
    and filing it again forced it into some other motif (until Oct 5)."""
    index = mi.load()
    entry = index['entries'].get(eid)
    found = next((c for c in (entry or {}).get('claims', []) if c['claim'] == claim), None)
    if found is None or answer not in ('yes', 'no', 'unsure'):
        raise ValueError(f'no such filing or answer: {eid} {answer}')
    if answer != 'no':
        if answer == 'yes' and found.get('checked') == 'yes':  # a second look: still fits (off that list)
            found['rechecked'] = dt.now().strftime('%Y-%m-%d')
        found['checked'] = answer
    else:
        k = mi.key(claim)
        entry['claims'].remove(found)
        entry.setdefault('not_claims', []).append(k)
        index['claims'][k] = [i for i in mi._ids(index, k) if i != eid]  # an empty list: no motif, and never refiled
        if not entry['claims'] and not entry.get('curated'):  # a model's motif emptied goes; one a person named stays
            del index['entries'][eid]
    mi.save(index)

@mi.exclusive
def group_add(name: str) -> str:
    index = mi.load()
    groups = index.setdefault('groups', {})
    gid = f"G{max([int(g[1:]) for g in groups] + [0]) + 1:02d}"
    groups[gid] = {'id': gid, 'name': mi.clean(name) or gid}
    mi.save(index)
    return gid


@mi.exclusive
def group_rename(gid: str, name: str):
    index = mi.load()
    index['groups'][gid]['name'] = mi.clean(name) or gid
    mi.save(index)


@mi.exclusive
def group_note(gid: str, note: str):
    """What the group's motifs have in common, in a sentence or two (the person's; the models read it), or none"""
    index = mi.load()
    note = ' '.join((note or '').split())
    if note:
        index['groups'][gid]['note'] = note
    else:
        index['groups'][gid].pop('note', None)
    mi.save(index)


@mi.exclusive
def group_delete(gid: str):
    """The group goes; its motifs stay, ungrouped"""
    index = mi.load()
    index.get('groups', {}).pop(gid, None)
    for e in index['entries'].values():
        if gid in mi.groups_of(e):
            mi._set_groups(e, [g for g in mi.groups_of(e) if g != gid])
    mi.save(index)


@mi.exclusive
def group_assign(eid: str, gid: str | None):
    """In this group only (or in none)"""
    index = mi.load()
    if gid and gid not in index.get('groups', {}):
        raise ValueError(f'no such group: {gid}')
    mi._set_groups(index['entries'][eid], [gid] if gid else [])
    mi._drafts(index['entries'][eid], groups=None)
    mi.save(index)


@mi.exclusive
def group_member(eid: str, gid: str, on: bool = True):
    """Into a group as well (keeping its others), or out of one"""
    index = mi.load()
    if gid not in index.get('groups', {}):
        raise ValueError(f'no such group: {gid}')
    entry = index['entries'][eid]
    mi._set_groups(entry, mi.groups_of(entry) + [gid] if on else [g for g in mi.groups_of(entry) if g != gid])
    if on:
        mi._drafts(entry, groups=[g for g in (entry.get('by_model') or {}).get('groups', []) if g != gid])
    mi.save(index)


@mi.exclusive
def facet_rename(facet: str, old: str, new: str):
    """A facet value renamed (a genre), on every motif that has it"""
    if facet not in mi.FACETS:
        raise ValueError(f'no such facet: {facet}')
    new = ' '.join(new.split())
    if not new or new == old:
        return
    index = mi.load()
    for e in mi.live(index):
        if (e.get('facets') or {}).get(facet) == old:
            e['facets'][facet] = new
    values = index.setdefault('facet_values', {}).setdefault(facet, [])
    index['facet_values'][facet] = [new if v == old else v for v in values] if old in values else values + [new]
    if old in mi.FACETS[facet]:
        index.setdefault('facet_hidden', {}).setdefault(facet, []).append(old)
    notes = index.get('facet_notes', {}).get(facet, {})
    if old in notes:
        notes[new] = notes.pop(old)
    mi.save(index)


@mi.exclusive
def facet_remove(facet: str, value: str):
    """A facet value gone (a genre): the motifs that had it have none"""
    if facet not in mi.FACETS:
        raise ValueError(f'no such facet: {facet}')
    index = mi.load()
    for e in mi.live(index):
        if (e.get('facets') or {}).get(facet) == value:
            e['facets'].pop(facet)
            if not e['facets']:
                e.pop('facets')
    values = index.setdefault('facet_values', {})  # (made here: the right side ran first and found none, Oct 7)
    values[facet] = [v for v in values.get(facet, []) if v != value]
    if value in mi.FACETS[facet]:
        index.setdefault('facet_hidden', {}).setdefault(facet, []).append(value)
    index.get('facet_notes', {}).get(facet, {}).pop(value, None)
    mi.save(index)


@mi.exclusive
def facet_note(facet: str, value: str, note: str):
    """A facet value's description (a genre's), or none"""
    if facet not in mi.FACETS:
        raise ValueError(f'no such facet: {facet}')
    index = mi.load()
    if value not in mi.facet_values(index)[facet]:
        raise ValueError(f'no such {facet}: {value}')
    note = ' '.join((note or '').split())
    notes = index.setdefault('facet_notes', {}).setdefault(facet, {})
    if note:
        notes[value] = note
    else:
        notes.pop(value, None)
    mi.save(index)


@mi.exclusive
def set_facet(eid: str, facet: str, value: str | None):
    """A motif's value in a facet (its genre), or none"""
    if facet not in mi.FACETS:
        raise ValueError(f'no such facet: {facet}')
    index = mi.load()
    entry = index['entries'][eid]
    value = ' '.join((value or '').split())
    if facet == 'genre':
        mi._drafts(entry, genre=None)
    if value:
        entry.setdefault('facets', {})[facet] = value
    else:
        entry.get('facets', {}).pop(facet, None)
        if not entry.get('facets'):
            entry.pop('facets', None)
    mi.save(index)


@mi.exclusive
def add_facet_value(facet: str, value: str):
    if facet not in mi.FACETS:
        raise ValueError(f'no such facet: {facet}')
    value = ' '.join(value.split())
    index = mi.load()
    values = index.setdefault('facet_values', {}).setdefault(facet, [])
    if value and value not in values and value not in mi.FACETS[facet]:
        values.append(value)
    mi.save(index)


@mi.exclusive
def no_motif(claim: str):
    """A person says this claim tells no recurring story: out of every motif it was in, kept out, and never filed
    again (an empty filing). A model's motif left empty goes, as on a 'no' in the motif check."""
    index = mi.load()
    k = mi.key(claim)
    for eid in list(mi._ids(index, k)):
        entry = index['entries'].get(eid)
        if not entry:
            continue
        entry['claims'] = [c for c in entry['claims'] if c['claim'] != claim]
        entry.setdefault('not_claims', []).append(k)
        if not entry['claims'] and not entry.get('curated'):
            del index['entries'][eid]
    index['claims'][k] = []
    mi.save(index)


@mi.exclusive
def withdraw(claim: str) -> list[str]:
    """Its source took the claim back (a Focus Group quote that doesn't support it): out of every motif and the claim
    list, so it isn't filed again or shown. A model's motif left empty goes. Returns the motifs it was in."""
    index = mi.load()
    k = mi.key(claim)
    was = []
    for eid in list(mi._ids(index, k)):
        entry = index['entries'].get(eid)
        if not entry:
            continue
        was.append(eid)
        entry['claims'] = [c for c in entry['claims'] if mi.key(c['claim']) != k]
        entry['done'] = [d for d in entry.get('done', []) if d != k]
        if not entry['claims'] and not entry.get('curated'):
            del index['entries'][eid]
    index['claims'].pop(k, None)
    mi.save(index)
    return was


@mi.exclusive
def unfile(claim: str, eid: str):
    """Take a claim out of a motif for good (as a no on the motif check)"""
    check.__wrapped__(claim, eid, 'no')


@mi.exclusive
def also_file(claim: str, source: str, target: str):
    """File a claim under another motif as well, keeping it where it is (a person's choice on the motif board)"""
    index = mi.load()
    k = mi.key(claim)
    found = next((c for c in index['entries'][source]['claims'] if mi.key(c['claim']) == k), None)
    entry = index['entries'][target]
    if found is None or entry.get('merged_into'):
        raise ValueError(f'no such claim in {source}, or {target} is gone')
    if not any(mi.key(c['claim']) == k for c in entry['claims']):  # a person filed it here: already checked
        entry['claims'].append(_for_motif(found))
    entry['not_claims'] = [x for x in entry.get('not_claims', []) if x != k]
    index['claims'][k] = list(dict.fromkeys(mi._ids(index, k) + [target]))
    mi.save(index)


# Done marks from the motif board: a person working through the index hides each motif once they've looked it over.
# A motif is done while every claim it holds was there when it was marked; a new claim brings it back.

@mi.exclusive
def mark_done(eid: str, done: bool = True):
    index = mi.load()
    entry = index['entries'][eid]
    if done:
        entry['done'] = sorted(mi.key(c['claim']) for c in entry['claims'])
        entry.pop('not_done', None)
        entry.pop('by_model', None)  # looked over: its genre and groups are the person's now
    else:
        entry.pop('done', None)
        entry['not_done'] = True  # unmarked by hand: a note saved later doesn't mark it done again
    mi.save(index)


@mi.exclusive
def reset_done():
    index = mi.load()
    for entry in index['entries'].values():
        entry.pop('done', None)
    mi.save(index)


@mi.exclusive
def reject(claim: str, eid: str):
    """A person says this claim isn't this motif: it's never suggested for it, or filed under it by the model"""
    index = mi.load()
    entry = index['entries'][eid]
    k = mi.key(claim)
    if k not in entry.setdefault('not_claims', []):
        entry['not_claims'].append(k)
    mi.save(index)


@mi.exclusive
def set_parent(eid: str, parent: str, on: bool = True):
    """`eid` rests (on) or doesn't rest (off) on `parent`. Refuses a loop."""
    index = mi.load()
    entries = index['entries']
    parents = mi.parents_of(entries[eid])
    if on:
        if parent not in entries or entries[parent].get('merged_into') or parent == eid:
            raise ValueError(f'no such motif: {parent}')
        todo, seen = [parent], set()
        while todo:  # everything above the new parent must not include eid
            p = todo.pop()
            if p == eid:
                raise ValueError(f'{parent} already rests on {eid}')
            if p not in seen:
                seen.add(p)
                todo += mi.parents_of(entries.get(p, {}))
        parents = list(dict.fromkeys(parents + [parent]))
        pair = sorted([eid, parent])  # related, so never suggested as a merge again
        if pair not in index.setdefault('not_same', []):
            index['not_same'].append(pair)
    else:
        parents = [p for p in parents if p != parent]
    entries[eid]['parents'] = parents
    entries[eid].pop('parent', None)
    mi.save(index)


# Related: two motifs that belong near each other without being one, or one a kind of the other ('Rape accusation
# against men' and 'Campus sexual assault controversy' meet on some events and are different stories). Both ways.
# A link can carry the person's reason ('a case of it, not a sibling'), kept beside the pairs in 'related_notes' so
# everything that reads the pairs reads them as before (Fable, Oct 12).

@mi.exclusive
def relate(a: str, b: str, related: bool = True, note: str | None = None):
    index = mi.load()
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
        if note is not None:  # an empty one takes the reason away
            note = ' '.join(note.split())
            notes = index.setdefault('related_notes', {})
            if note:
                notes['|'.join(pair)] = note
            else:
                notes.pop('|'.join(pair), None)
    else:
        index['related'] = [p for p in links if p != pair]
    mi.save(index)


@mi.exclusive
def correct_claim(old: str, new: str):
    new = ' '.join(new.split())
    index = mi.load()
    ko, kn = mi.key(old), mi.key(new)
    if not new or new == old:
        return
    if ko not in index['claims']:
        raise ValueError('no such claim in the index')
    for e in index['entries'].values():
        for c in e['claims']:
            if mi.key(c['claim']) == ko:
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
    if ko in index.get('held', {}):  # a held claim stays held in its new words
        index['held'][kn] = {**index['held'].pop(ko), 'claim': new}
    mi.save(index)


@mi.exclusive
def same_claim(variant: str, canonical: str):
    """A person says two claims are one claim told two ways. The variant folds into the kept claim in every motif either
    was in; its words are kept on the kept claim's record as a variant (with where they came from); and later tellings
    in exactly its words are filed as the kept claim (through the corrections). The variant may be one not filed yet."""
    index = mi.load()
    kv, kc = mi.key(variant), mi.key(canonical)
    if kv == kc:
        raise ValueError('that is the same claim')
    if kc not in index['claims']:
        raise ValueError('the claim to keep is not in the index')
    entries = index['entries']
    ids_v, ids_c = mi._ids(index, kv), mi._ids(index, kc)
    template = next((c for eid in ids_c if eid in entries for c in entries[eid]['claims'] if mi.key(c['claim']) == kc), None)
    told = {'claim': variant}
    for eid in dict.fromkeys(ids_v + ids_c):
        e = entries.get(eid)
        if not e:
            continue
        vrec = next((c for c in e['claims'] if mi.key(c['claim']) == kv), None)
        crec = next((c for c in e['claims'] if mi.key(c['claim']) == kc), None)
        if vrec:
            e['claims'].remove(vrec)
            told = {k: vrec[k] for k in ('claim', 'source', 'ref', 'date') if vrec.get(k)}
            if crec is None:
                crec = {k: v for k, v in (template or vrec).items() if k not in ('variants', 'checked')}
                crec['claim'] = canonical
                e['claims'].append(crec)
            crec['variants'] = crec.get('variants', []) + vrec.get('variants', [])
            if crec.get('story') is None and vrec.get('story') is not None:  # the variant's story, if the kept has none
                crec.update({f: vrec[f] for f in mi.STORY_FIELDS if vrec.get(f) is not None})
            told.update({f: vrec[f] for f in mi.STORY_FIELDS if vrec.get(f) is not None})
        if e.get('done') and kv in e['done']:
            e['done'] = sorted((set(e['done']) - {kv}) | {kc})
        if kv in e.get('not_claims', []):
            e['not_claims'] = list(dict.fromkeys(kc if k == kv else k for k in e['not_claims']))
    for eid in dict.fromkeys(ids_c + ids_v):  # the variant's words on every record of the kept claim
        crec = next((c for c in entries.get(eid, {}).get('claims', []) if mi.key(c['claim']) == kc), None)
        if crec is not None and all(v.get('claim') != variant for v in crec.get('variants', [])):
            crec.setdefault('variants', []).append(told)
    index['claims'][kc] = list(dict.fromkeys(ids_c + ids_v))
    index['claims'].pop(kv, None)
    if kv in index.get('held', {}):  # a held variant holds the kept claim
        index['held'].setdefault(kc, {**index['held'][kv], 'claim': canonical})
        index['held'].pop(kv)
    fixes = index.setdefault('corrections', {})
    for original, current in list(fixes.items()):  # earlier wordings of the variant lead to the kept claim now
        if current == variant:
            fixes[original] = canonical
    fixes[variant] = canonical
    mi.save(index)


@mi.exclusive
def story_for(claim: dict, index: dict) -> dict:
    """A claim's story fields for a filing made by hand (the curation session, Oct 12: hand filings and 💡 new motifs
    dropped them): from the claim given, else another filing of it, else the watch list, else (a posts claim) the
    report it came in, its ref being the report's time"""
    have = {f: claim[f] for f in mi.STORY_FIELDS if claim.get(f) is not None}
    if have:
        return have
    k = mi.key(claim['claim'])
    for eid in mi._ids(index, k):
        for c in index['entries'].get(eid, {}).get('claims', []):
            if mi.key(c['claim']) == k and c.get('story') is not None:
                return {f: c[f] for f in mi.STORY_FIELDS if c.get(f) is not None}
    try:
        from app.analysis import watch_list
        w = watch_list.load()['claims'].get(k) or {}
        if w.get('story') is not None:
            return {'story': w['story'], **({'story_tie': w['story_tie']} if w.get('story_tie') else {})}
    except Exception:  # noqa: BLE001 - no watch list yet
        pass
    ref = claim.get('ref') or ''
    if claim.get('source') == 'narrative' and ref:
        import glob
        from app import narratives
        name = f'report-{ref[:10]}-{ref[11:13]}{ref[14:16]}*.json'  # 2026-10-05T08:17 -> report-2026-10-05-0817.json
        for path in glob.glob(os.path.join(narratives.FOLDER, name)):
            for g in read_json(path, {}).get('found', []):
                said = (g.get('label') or {}).get('narrative')
                if said and k in (mi.key(said), mi.key(mi.corrected(said, index))):
                    if not g.get('story'):  # the model left it untied: the story its posts link to
                        known = narratives.articles([u for u, _ in g.get('shared') or []])
                        g = {**g, 'story': narratives.linked_story(
                            {'articles': [{**known[u], 'shares': n} for u, n in g.get('shared') or [] if u in known]})}
                    return mi.story_of_group(g)
    return {}


def file_by_hand(claim: dict, eid: str):
    """File a claim (one not in the index yet, or already elsewhere) under a motif a person chose"""
    index = mi.load()
    entry = index['entries'][eid]
    if entry.get('merged_into'):
        raise ValueError(f'{eid} is gone')
    k = mi.key(claim['claim'])
    if not (claim.get('source') or claim.get('ref')) and not mi._json_mode():  # a claim out of every motif: where it
        from app.analysis import motif_db  # came from is in the change log
        keys = {mi.key(t) for t in mi.originals(claim['claim'], index)}
        claim = {**claim, **{f: v for f, v in motif_db.last_origin(mi.INDEX, keys).items() if f in ('source', 'ref')}}
    if not any(mi.key(c['claim']) == k for c in entry['claims']):
        entry['claims'].append({'claim': claim['claim'], 'source': claim.get('source', ''), 'ref': claim.get('ref', ''),
                                'date': dt.now().strftime('%Y-%m-%d'), 'checked': 'yes',  # a person's filing
                                **story_for(claim, index)})
    entry['not_claims'] = [x for x in entry.get('not_claims', []) if x != k]
    index['claims'][k] = list(dict.fromkeys(index['claims'].get(k, []) + [eid]))
    mi.save(index)


@mi.exclusive
def stands_alone(eid: str, alone: bool = True):
    """A person says this single-claim motif is right on its own: it leaves the singles list"""
    index = mi.load()
    if alone:
        index['entries'][eid]['stands_alone'] = True
    else:
        index['entries'][eid].pop('stands_alone', None)
    mi.save(index)


@mi.exclusive
def set_note(eid: str, note: str):
    """A person's scope note for a motif: one plain line on what it covers, beside its name (used in matching and
    shown on the site); empty removes it"""
    index = mi.load()
    note = ' '.join(note.split())
    entry = index['entries'][eid]
    if note:
        entry['note'], entry['note_by'] = note, 'person'
        mi.done_by_note(entry)
    else:
        entry.pop('note', None)
        entry.pop('note_by', None)
    mi.save(index)


@mi.exclusive
def set_not_this(eid: str, text: str):
    """What a motif isn't, though it looks like it ('not a scandal's cover-up, only the scandal'): a person's line,
    shown to the filing model and the judge beside the note (motif_index.REUSE_PROMPT, motif_signals.judge_ask) and to
    the element drafter; empty removes it"""
    index = mi.load()
    text = ' '.join(text.split())
    entry = index['entries'][eid]
    if text:
        entry['not_this'] = text
    else:
        entry.pop('not_this', None)
    mi.save(index)


@mi.exclusive
def set_carrying(claim: str, eid: str, text):
    """The tellers' own words that carry the motif in this filing ("religion of peace", said sarcastically, under the
    Dublin crowd claim): a person's, per filing (praxis rule 1's carrying words), the source of each motif's phrase
    dictionary (carrying()). Oct 13, the person asked for it; empty takes them away"""
    index = mi.load()
    found = next((c for c in index['entries'][eid]['claims'] if mi.key(c['claim']) == mi.key(claim)), None)
    if found is None:
        raise ValueError(f'no such filing: {eid} {claim[:60]}')
    phrases = mi.phrases_in(text)
    if phrases:
        found['carrying'] = phrases
    else:
        found.pop('carrying', None)
    mi.save(index)


def keep_note(eid: str):
    """A person keeps the model's drafted note as it is: it's theirs now, and shown on the site"""
    index = mi.load()
    if index['entries'][eid].get('note'):
        index['entries'][eid]['note_by'] = 'person'
        mi.done_by_note(index['entries'][eid])
        mi.save(index)
