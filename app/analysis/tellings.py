"""A flabby motif opened into its tellings (Oct 14, Pandora in production; the person: "I 100% want to do the pandora",
8 of the first 10 of Gemma's tellings "amazing"; and "making motif generation more specific, i.e. splitting flabby
motifs"). Pandora (scripts/experiments/f10_pandora.py) had Gemma open each of the person's motifs of 10+ claims and
name the distinct tellings inside, each with a note and its claims: 227 tellings of 36 motifs, drafted.

In the checker's 🧩 tellings tab the person takes them a motif at a time. A telling made a motif is curated, carries
its note, rests on the motif it came from (the one hierarchy link: a case of it), and gets the ticked claims, checked.
By default the claims leave the broader motif (narrowing it, which is the point), but not as a "move": a move out of a
motif is read by the confidence model as "not this motif" (filing_confidence._decided), and these claims are still
instances of the broader shape, only placed more exactly. So the action is its own, 'telling', which the model reads
as no verdict on the broader motif, and the claim isn't marked as kept out of it. A telling turned down ('not a
telling') is recorded too. Both are Pandora's verdicts as well, so the experiment's tally grows from daily use."""
import json
import os

from app.analysis import motif_index as mi
from app.utils import Config, get_logger

logger = get_logger(__name__)

PANDORA = os.path.join(Config.data, 'motifs', 'experiments', 'f10_pandora.json')


def _pandora() -> dict:
    try:
        with open(PANDORA) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _verdict(key: str, value: str):
    """Pandora's record of the person's word on a telling ('motif' or 'not')"""
    s = _pandora()
    if not s:
        return
    s.setdefault('verdicts', {})[key] = value
    with open(PANDORA + '.tmp', 'w') as f:
        json.dump(s, f, indent=1)
    os.replace(PANDORA + '.tmp', PANDORA)


def drafted(index: dict | None = None) -> list[dict]:
    """The motifs with tellings still to decide, the most claims first: each {id, name, note, claims, tellings: [{key,
    name, note, claims: the telling's claims still in the motif}]}; tellings decided, or with none of their claims left
    in the motif, left out"""
    index = index if index is not None else mi.load()
    s = _pandora()
    verdicts = s.get('verdicts', {})
    out = []
    for mid, m in (s.get('motifs') or {}).items():
        e = index['entries'].get(mid)
        if not e or e.get('merged_into'):
            continue
        have = {mi.key(c['claim']): c['claim'] for c in e.get('claims', [])}
        tellings = []
        for g in m.get('groups', []):
            key = f"{mid}|{g['name']}"
            claims = [have[mi.key(c)] for c in g.get('claims', []) if mi.key(c) in have]
            if key not in verdicts and claims:
                tellings.append({'key': key, 'name': g['name'], 'note': g.get('note', ''), 'claims': claims})
        if tellings:
            out.append({'id': mid, 'name': e['name'], 'note': e.get('note', ''), 'claims': len(e.get('claims', [])),
                        'tellings': tellings})
    return sorted(out, key=lambda m: -m['claims'])


@mi.exclusive
def make(parent: str, name: str, claims: list[str], note: str = '', move: bool = True, key: str | None = None) -> str:
    """A telling of `parent` made a motif: curated, with its note, resting on `parent`, the claims filed in it (checked:
    a person put them there) and, with `move`, out of `parent` (not as a move: see the module's note). Its id"""
    name = ' '.join((name or '').split())
    if not name:
        raise ValueError('a telling needs a name')
    index = mi.load()
    if parent not in index['entries'] or index['entries'][parent].get('merged_into'):
        raise ValueError(f'no such motif: {parent}')
    eid = mi._add(name)  # already holding the lock
    index = mi.load()
    entries = index['entries']
    src, dst = entries[parent], entries[eid]
    if note.strip():
        dst['note'], dst['note_by'] = ' '.join(note.split()), 'person'
    dst['parents'] = [parent]
    wanted = {mi.key(c) for c in claims}
    for c in [c for c in src['claims'] if mi.key(c['claim']) in wanted]:
        k = mi.key(c['claim'])
        dst['claims'].append({**{f: v for f, v in c.items() if f not in ('checked', 'fit', 'rechecked')}, 'checked': 'yes'})
        ids = mi._ids(index, k)
        if move:
            src['claims'].remove(c)
            ids = [i for i in ids if i != parent]
        index['claims'][k] = list(dict.fromkeys(ids + [eid]))
    mi.save(index)
    if key:
        _verdict(key, 'motif')
    logger.info("Telling %s of %s made a motif: %s (%d claims, %s)", eid, parent, name, len(dst['claims']),
                'moved' if move else 'kept in both')
    return eid


def reject(key: str):
    """A telling the person turned down: not a telling"""
    if not isinstance(key, str) or '|' not in key:
        raise ValueError('reject: a telling')
    _verdict(key, 'not')
