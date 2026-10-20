"""What the checker's 🧠 Live page shows (scripts/checker/templates/live.html; served at /live.json): the filing
pipeline as it runs, from its trace (app/analysis/trace.py), and each claim's whole journey through it with the real
data at every stage.

    /live.json                 the stages, the recent events (the trace's and the person's decisions from the curation
                               log), counts per stage per hour over the last day, and good examples to open
    /live.json?since=<time>    only the events since then, and the counts (the page polls this)
    /live.json?claim=<key>     one claim's journey (its key, #id: the first 6 characters of it, or its words)
    /live.json?q=<words>       claims to open, by their words or #id

A claim filed before tracing began (Oct 14) is rebuilt from what the logs kept: the shortlist and refile logs (the
motifs shown and picked), the motif signals' caches (its shape and layers), the filings' fit and checks, the curation
log (the person's decisions, with the fit each had then), and where it came from (the checker's claim_detail). What no
log kept (the signals behind a shortlist, the confidence model's reasons) is said to be missing, never worked out
again: this reads stored data only and never calls a model."""
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime as dt
from datetime import timedelta as td

from app.analysis import trace
from app.utils import get_logger

logger = get_logger(__name__)

STAGES = [
    {'id': 'written', 'emoji': '✍️', 'name': 'claim written',
     'what': "A sentence written for what people tell: from a group of posts that say one thing, a fact-check's piece, "
             "or claims told on two or more shows"},
    {'id': 'shaped', 'emoji': '🧩', 'name': 'shape & layers',
     'what': 'The filing model restates the claim as the bare shape of its story, and layer by layer (character, plot, '
             'theory, argument, value)'},
    {'id': 'shortlist', 'emoji': '🔦', 'name': 'shortlist',
     'what': 'Every motif scored against the claim on some twenty signals, weighed by weights learned from your '
             'filings: the best eight, what they rest on, and two seeds are shown to the filing model'},
    {'id': 'picked', 'emoji': '🤖', 'name': 'filing model picks',
     'what': 'Gemma 26B reads the shortlist side by side and picks the motifs the claim is clearly another instance of, '
             'or names a new one'},
    {'id': 'scored', 'emoji': '🎯', 'name': 'confidence',
     'what': "Each filing in your motifs gets a fit: the chance you'd keep it, from signals weighed on your own checks"},
    {'id': 'decided', 'emoji': '🧑', 'name': 'your verdict',
     'what': 'You keep it, take it out, move it, add a motif, reword or split it'},
    {'id': 'refiled', 'emoji': '♻️', 'name': 'refiled',
     'what': 'A claim with no motif, or only plain news, filed again against the grown index'},
    {'id': 'split', 'emoji': '✂️', 'name': 'split',
     'what': 'A claim whose posts tell several things, split into one claim per telling'},
]
STAGE_OF = {'split_proposed': 'split'}

# Every signal the shortlist's learned weights and the confidence model read, in plain words (from the code's own
# comments: motif_retriever.FACTS, motif_signals' docstring, filing_confidence.FEATURES)
GLOSSARY = {
    'today': ("the plain score", "the older shortlist's score: six likeness measures weighed together"),
    'text': ('like the motif', 'how alike the claim is to the motif as a whole: its name, note, phrases and two claims'),
    'name and note': ('like its name', "how alike the claim is to the motif's name and scope note"),
    'nearest claim': ('like its nearest claim', "how alike the claim is to the motif's closest filed claim"),
    'center of claims': ('like its claims', "how alike the claim is to the average of the motif's claims"),
    'size': ('motif size', 'how many claims the motif holds (bigger motifs are more often right)'),
    'tree': ('like its family', 'the best likeness among the motifs it rests on and those resting on it'),
    'keywords': ('shared words', "distinctive words shared with the motif's name, note and claims (BM25)"),
    'note': ('like its note', "the claim against the motif's scope note alone, by meaning"),
    'shape': ("shape like its note", "the claim's bare shape (no names, places or dates) against the motif's note"),
    'votes': ('nearest claims vote', 'the 15 filed claims most like this one, each voting for the motifs it is in'),
    'nomic desc': ('2nd embedder: motif', "a second embedding model (nomic) reading the motif's name and note"),
    'nomic near': ('2nd embedder: nearest claim', "the second embedding model on the motif's closest claim"),
    'group': ('like its group', "the claim against the center of your group the motif is in (-1: in no group)"),
    'news out note': ('note, news taken out', "the note's likeness with the day's news topics projected away: framing, "
                      'not topic'),
    'news out near': ('nearest claim, news taken out', "the closest claim's likeness with the day's news topics projected "
                      'away'),
    'layers best': ('best layer', "the best of the claim's layers (character, plot, theory, argument, value) against "
                    'the note'),
    'layer of its genre': ("its genre's layer", "the claim's layer that goes with the motif's genre (its plot for a "
                           'Plot, its theory for a Theory) against the note'),
    'qwen3 8b note': ('Qwen3 8B: note', "Qwen3-Embedding 8B: the claim against the motif's name and note"),
    'qwen3 8b near': ('Qwen3 8B: nearest claim', "Qwen3-Embedding 8B: the claim against the motif's closest claim"),
    'arctic2 note': ('Arctic 2: note', "Snowflake Arctic Embed 2: the claim against the motif's name and note"),
    'arctic2 near': ('Arctic 2: nearest claim', "Snowflake Arctic Embed 2: the claim against the motif's closest claim"),
    'score': ('shortlist score', "the plain shortlist's score for this motif"),
    'rank': ('shortlist rank', 'where the motif ranks among all motifs for this claim (log; lower is nearer the top)'),
    'margin': ('lead over the next', "how far this motif's score is ahead of (or behind) the claim's best other motif"),
    'motifs of the claim': ('motifs it is in', 'how many motifs the claim is filed in'),
    'from narrative': ('from posts', 'the claim came from what people post'),
    'from Focus Group': ('from the Focus Group', 'the claim came from the Focus Group'),
    'rerank': ('reranker says yes', 'a cross-encoder (Qwen3 Reranker) reading the claim and motif together: yes or no '
               '(log-odds)'),
    'judge': ('judge says yes', 'Nimble 9B asked whether the claim is an instance of the motif, given what the motif '
              'must contain: its yes (log-odds)'),
}
FEED = 150  # events sent at first
STREAM_DAYS = 2  # days of the trace the live feed reads
EXAMPLES = 8  # claims a kind of example
TEXT = 400

_cache = {}
_files = {}


# ---------- reading what's stored, each kept until its file changes ----------

def _stamp(*paths) -> tuple:
    out = []
    for p in paths:
        try:
            st = os.stat(p)
            out.append((p, st.st_mtime_ns, st.st_size))
        except OSError:
            out.append((p, None))
    return tuple(out)


def _cached(name: str, stamp, make):
    hit = _cache.get(name)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    value = make()
    _cache[name] = (stamp, value)
    return value


def _read_file(path: str) -> list[dict]:
    """A trace file's events, read on from where the last read stopped (it only grows)"""
    try:
        size = os.path.getsize(path)
    except OSError:
        return []
    done, events = _files.get(path, (0, []))
    if size < done:  # rewritten: from the top
        done, events = 0, []
    if size > done:
        with open(path, 'rb') as f:
            f.seek(done)
            chunk = f.read(size - done)
        end = chunk.rfind(b'\n') + 1  # a line still being written waits for the next read
        new = []
        for line in chunk[:end].splitlines():
            try:
                new.append(json.loads(line))
            except ValueError:
                continue
        done, events = done + end, events + new
        _files[path] = (done, events)
    return events


def trace_events(days: int | None = None) -> list[dict]:
    """The trace's events, oldest first (the last `days` days' files, or all kept)"""
    paths = sorted(glob.glob(os.path.join(trace.folder(), '*.jsonl')))
    if days is not None:
        cut = f'{dt.now() - td(days=days - 1):%Y-%m-%d}'
        paths = [p for p in paths if os.path.basename(p)[:10] >= cut]
    events = [e for p in paths for e in _read_file(p)]
    # Filings of claims that never reached the live index came from an experiment filing into a copy of it (the night
    # of Oct 14-15, Rip Van Winkle's 687 sandbox filings, before experiments stopped tracing): not the pipeline's
    known = set(_index().get('claims', {})) | set(_index().get('tellings', {}))
    return [e for e in events if e.get('s') not in FILING_STAGES or e.get('k') in known]


FILING_STAGES = {'shaped', 'shortlist', 'picked', 'scored'}


def _index_stamp() -> tuple:
    from app.analysis import motif_index as mi
    return _stamp(mi.INDEX)


def _index() -> dict:
    from app.analysis import motif_index as mi
    return _cached('index', _index_stamp(), mi.load)


def _log_stamp() -> tuple:
    from app.analysis import curation_db, filing_confidence as fc
    return _stamp(curation_db.DB, curation_db.DB + '-wal', fc.CURATION_LOG)


def _log() -> list[dict]:
    from app.analysis import filing_confidence as fc
    return _cached('log', _log_stamp(), lambda: fc.log_rows(fc.CURATION_LOG))  # the path as it is now (tests move it)


def _jsonl(path: str) -> list[dict]:
    def read():
        out = []
        try:
            with open(path) as f:
                for line in f:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        continue
        except OSError:
            pass
        return out
    return _cached(path, _stamp(path), read)


def _json(path: str, default):
    from app.utils.store import read_json
    return _cached(path, _stamp(path), lambda: read_json(path, default))


def _shortlist_log() -> list[dict]:
    from app.analysis import motif_index as mi
    return _jsonl(mi.SHORTLIST_LOG)


def _refile_log() -> list[dict]:
    from app.analysis import watch_list
    return _jsonl(watch_list.REFILE_LOG)


# ---------- the person's decisions, from the curation log ----------

def _verdicts(s: dict) -> list[dict]:
    """The filings one logged step decides or changes: {claim, id, kept (True, False, None), act, ...}"""
    act, c = s.get('action'), s.get('claim')
    why = s.get('why')
    out = []
    if act == 'new_with':
        for x in s.get('claims') or []:
            if isinstance(x, dict) and isinstance(x.get('claim'), str):
                if x.get('mode') == 'move' and x.get('source'):
                    out.append({'claim': x['claim'], 'id': x['source'], 'kept': False, 'act': 'moved out', 'name': s.get('name')})
                out.append({'claim': x['claim'], 'id': None, 'kept': True, 'act': 'into a new motif', 'name': s.get('name')})
        return out
    if not isinstance(c, str) or not c:
        return out
    if act == 'check' and s.get('answer') in ('yes', 'no', 'unsure'):
        out.append({'claim': c, 'id': s.get('id'), 'kept': {'yes': True, 'no': False}.get(s['answer']), 'act': 'check'})
    elif act in ('unfile', 'reject', 'not this motif'):
        out.append({'claim': c, 'id': s.get('id'), 'kept': False, 'act': act})
    elif act == 'move':
        out += [{'claim': c, 'id': s.get('source'), 'kept': False, 'act': 'moved out', 'to': s.get('target')},
                {'claim': c, 'id': s.get('target'), 'kept': True, 'act': 'moved in', 'from': s.get('source')}]
    elif act == 'also':
        out.append({'claim': c, 'id': s.get('target'), 'kept': True, 'act': 'added'})
    elif act in ('also_new', 'move_new'):
        if act == 'move_new':
            out.append({'claim': c, 'id': s.get('source'), 'kept': False, 'act': 'moved out'})
        out.append({'claim': c, 'id': None, 'kept': True, 'act': 'into a new motif', 'name': s.get('name')})
    elif act == 'file':
        out.append({'claim': c, 'id': s.get('id'), 'kept': True, 'act': 'filed by hand'})
    elif act == 'no_motif':
        out.append({'claim': c, 'id': None, 'kept': None, 'act': 'tells no story'})
    elif act == 'correct' and isinstance(s.get('text'), str):
        out.append({'claim': c, 'id': None, 'kept': None, 'act': 'reworded', 'to': s['text']})
    elif act == 'split':
        out.append({'claim': c, 'id': None, 'kept': None, 'act': 'split', 'children': s.get('children') or []})
    elif act == 'carrying' and s.get('id'):
        out.append({'claim': c, 'id': s['id'], 'kept': None, 'act': 'carrying words', 'to': s.get('text')})
    for v in out:
        if why:
            v['why'] = why
    return out


def decided_events(rows: list[dict]) -> list[dict]:
    """Each filing the person (or Claude on their word) decided, as an event of the 'decided' stage ('split' for a
    split), with the fit it had then and whether it was passed as sure (a batch of ✓ checks, each at or past the sure
    line)"""
    out = []
    for r in rows:
        a = r.get('action')
        if not isinstance(a, dict) or not r.get('at'):
            continue
        before = r.get('before') if isinstance(r.get('before'), dict) else {}
        fits, sure_at = before.get('fits') or {}, before.get('sure_at')
        steps = [s for s in (a.get('steps') or []) if isinstance(s, dict)] if a.get('action') == 'batch' else [a]
        vs = [v for s in steps for v in _verdicts(s)]
        fit = lambda v, fits=fits: fits.get(f"{trace.key(v['claim'])}|{v['id']}") if v.get('id') else None  # noqa: E731
        sure = bool(sure_at) and bool(vs) and all(v['act'] == 'check' and v['kept'] is True and (fit(v) or 0) >= sure_at
                                                  for v in vs)
        for v in vs:
            e = {'t': r['at'], 's': 'split' if v['act'] == 'split' else 'decided', 'k': trace.key(v['claim']),
                 'c': v['claim'][:TEXT], 'by': r.get('by') or 'person', 'fit': fit(v), 'sure_at': sure_at,
                 'sure': sure or None, 'batch': a.get('why') if a.get('action') == 'batch' else None,
                 **{f: v[f] for f in ('id', 'kept', 'act', 'why', 'name', 'to', 'from', 'children') if v.get(f) is not None}}
            if 'kept' in v:
                e['kept'] = v['kept']
            out.append(e)
    return out


def _decided() -> list[dict]:
    return _cached('decided', _log_stamp(), lambda: decided_events(_log()))


# ---------- the stream ----------

def _names(index: dict) -> dict:
    from app.analysis import motif_index as mi

    def make():
        out = {}
        for eid, e in index['entries'].items():
            to = mi.resolve(index, eid)
            t = index['entries'].get(to, e)
            out[eid] = {'name': t['name'], 'genre': mi.genre_of(t), **({'now': to} if to != eid else {})}
        return out
    return _cached('names', _index_stamp(), make)


def _name(names: dict, eid) -> str:
    return (names.get(eid) or {}).get('name') or str(eid)


def line(e: dict, names: dict) -> str:
    """An event in a few words, for the feed"""
    s = e.get('s')
    n = lambda ids: ', '.join(_name(names, i) for i in ids or [])  # noqa: E731
    if s == 'written':
        if e.get('source') == 'narrative':
            return f"from {e.get('posts', '?')} posts by {e.get('authors', '?')} people"
        if e.get('source') == 'shows':
            return f"told on {len(e.get('shows') or [])} shows ({e.get('tellings', '?')} tellings)"
        return f"from a fact-check by {e.get('source', '?')}"
    if s == 'shaped':
        return e.get('shape') or 'its layers'
    if s == 'shortlist':
        return (f"{len(e.get('shown') or [])} motifs shown" + (f" of {e['of']}" if e.get('of') else '')
                + f" ({e.get('method', '?')})" + (' · refiling' if e.get('refile') else ''))
    if s == 'picked':
        if e.get('picked'):
            return 'picked ' + n(e['picked'])
        if e.get('made'):
            return 'made a new motif: ' + n(e['made'])
        if e.get('filed'):
            return 'named it as ' + n(e['filed'])
        return 'no motif fits' + (f" (offered {', '.join(e['new'])})" if e.get('new') else '')
    if s == 'scored':
        return ', '.join(f"{_name(names, i)} {round(100 * f)}%" for i, f in zip(e.get('ids') or [], e.get('fit') or []))
    if s == 'decided':
        m = _name(names, e['id']) if e.get('id') else e.get('name') or ''
        word = {'check': '✓ kept in' if e.get('kept') else '✕ taken out of' if e.get('kept') is False else '🤷 unsure of',
                'moved out': '↪ moved out of', 'moved in': '↪ moved into', 'added': '➕ added to',
                'into a new motif': '🆕 put in a new motif', 'filed by hand': '✋ filed by hand in',
                'unfile': '✕ taken out of', 'reject': '✕ rejected from', 'not this motif': '✕ not',
                'tells no story': '🚫 tells no story', 'reworded': '✏️ reworded', 'carrying words': '🗣️ carrying words in'}
        return f"{word.get(e.get('act'), e.get('act'))} {m}".strip() + (' · 🎯 passed as sure' if e.get('sure') else '')
    if s == 'refiled':
        return f"{e.get('outcome', 'refiled')}" + (f": {n(e['filed'])}" if e.get('filed') else '')
    if s == 'split':
        return f"split into {len(e.get('children') or [])}"
    if s == 'split_proposed':
        return 'organizer: ' + ('split proposed' if e.get('split') else 'no split')
    return ''


def _feed(e: dict, names: dict) -> dict:
    out = {'t': e['t'], 's': STAGE_OF.get(e['s'], e['s']), 'k': e['k'], 'c': e.get('c', ''), 'line': line(e, names)}
    if e.get('sure'):
        out['sure'] = True
    if e['s'] == 'decided' and e.get('kept') is not None:
        out['kept'] = e['kept']
    return out


def events(days: int = STREAM_DAYS) -> list[dict]:
    """The trace's events and the person's decisions of the last `days`, oldest first; a split the curation log
    has stands for the trace's own record of it"""
    cut = f'{dt.now() - td(days=days):%Y-%m-%dT%H:%M:%S}'
    dec = [e for e in _decided() if e['t'] >= cut]
    logged_splits = {e['k'] for e in dec if e['s'] == 'split'}
    tr = [e for e in trace_events(days + 1) if e.get('t', '') >= cut and not (e.get('s') == 'split' and e['k'] in logged_splits)]
    out = sorted(tr + dec, key=lambda e: e['t'])
    texts = {}
    for e in out:  # a scoring's claim words from its shortlist, or the index
        if e.get('c'):
            texts[e['k']] = e['c']
    missing = {e['k'] for e in out if not e.get('c') and e['k'] not in texts}
    if missing:
        from app.analysis import motif_index as mi
        for e in mi.live(_index()):
            for c in e['claims']:
                k = mi.key(c['claim'])
                if k in missing:
                    texts[k] = c['claim'][:TEXT]
    for e in out:
        if not e.get('c') and e['k'] in texts:
            e['c'] = texts[e['k']]
    return out


def counts(evs: list[dict], hours: int = 24) -> dict:
    """Events per stage per hour, the last `hours` (the oldest first), and per stage in the last hour"""
    now = dt.now()
    start = (now - td(hours=hours - 1)).replace(minute=0, second=0, microsecond=0)
    labels = [(start + td(hours=h)) for h in range(hours)]
    per = {s['id']: [0] * hours for s in STAGES}
    for e in evs:
        try:
            h = int((dt.fromisoformat(e['t']) - start).total_seconds() // 3600)
        except (ValueError, KeyError):
            continue
        s = STAGE_OF.get(e.get('s'), e.get('s'))
        if 0 <= h < hours and s in per:
            per[s][h] += 1
    hour_ago = f'{now - td(hours=1):%Y-%m-%dT%H:%M:%S}'
    last = Counter(STAGE_OF.get(e.get('s'), e.get('s')) for e in evs if e.get('t', '') >= hour_ago)
    return {'hours': [f'{h:%H}' for h in labels], 'per_hour': per, 'last_hour': {s['id']: last.get(s['id'], 0) for s in STAGES},
            'day': {s: sum(v) for s, v in per.items()}}


def stream(params: dict) -> dict:
    index = _index()
    names = _names(index)
    evs = events()
    since = params.get('since')
    shown = [e for e in evs if e['t'] >= since][-400:] if since else evs[-FEED:]
    out = {'now': dt.now().isoformat(timespec='seconds'), 'events': [_feed(e, names) for e in shown],
           'counts': counts(evs), 'traced_since': _traced_since()}
    if not since:
        out.update(stages=STAGES, examples=examples(), glossary={k: list(v) for k, v in GLOSSARY.items()})
    return out


# ---------- good examples, and finding a claim ----------

def _filed_passes() -> list[dict]:
    """Each filing pass over a claim, oldest first: {'t', 'k', 'c', 'shown', 'picked', 'new', 'made', 'next'}: the
    shortlist log, and the trace where it has more"""
    out = {}
    for r in _shortlist_log():
        out[(r.get('key'), r.get('at', '')[:16])] = {'t': r.get('at', ''), 'k': r.get('key'), 'c': r.get('claim', ''),
                                                     'shown': r.get('shown') or [], 'picked': r.get('picked') or [],
                                                     'new': r.get('new') or [], 'next': r.get('next')}
    for e in trace_events():
        if e.get('s') == 'picked' and not e.get('refile'):
            p = out.setdefault((e['k'], e['t'][:16]), {'t': e['t'], 'k': e['k'], 'c': e.get('c', ''), 'shown': [],
                                                       'picked': e.get('picked') or [], 'new': e.get('new') or []})
            p['made'] = e.get('made') or []
    return sorted(out.values(), key=lambda p: p['t'])


def examples() -> dict:
    """Claims worth opening, the newest first, a few of each kind"""
    index = _index()
    names = _names(index)
    dec = _decided()
    passes = _filed_passes()

    def pick(items, n=EXAMPLES):
        seen, out = set(), []
        for x in sorted(items, key=lambda x: x['t'], reverse=True):
            if x['k'] not in seen and x.get('c'):
                seen.add(x['k'])
                out.append({'k': x['k'], 'c': x['c'][:TEXT], 't': x['t'], 'note': x.get('note', '')})
            if len(out) >= n:
                break
        return out
    shown = defaultdict(set)
    nxt = {}
    for p in passes:
        shown[p['k']] |= set(p['shown'])
        nxt.setdefault(p['k'], p.get('next'))

    def existed(eid: str, k: str) -> bool:
        n = nxt.get(k)
        m = re.fullmatch(r'M(\d+)', eid or '')
        return bool(m and n and int(m.group(1)) < n)
    unshown = [{**e, 'note': f"→ {_name(names, e['id'])}, not on its shortlist"} for e in dec
               if e['s'] == 'decided' and e.get('kept') is True and e.get('id') and e['k'] in shown
               and e['id'] not in shown[e['k']] and existed(e['id'], e['k'])]
    made = [{**p, 'note': '🆕 ' + ', '.join(_name(names, i) for i in p['made']) if p.get('made') else
             '🆕 ' + ', '.join(p['new'])} for p in passes if not p['picked'] and (p.get('made') or p['new'])]
    refiled = [{'t': r['at'], 'k': r['key'], 'c': r['claim'], 'note': '♻️ ' + ', '.join(_name(names, i) for i in r['filed'])}
               for r in _refile_log() if r.get('filed') and r.get('key')]
    splits = [{'t': t.get('at', ''), 'k': k, 'c': t.get('claim', ''), 'note': f"✂️ into {len(t.get('children') or [])}"}
              for k, t in index.get('tellings', {}).items()]
    return {
        'recent': pick([{**p, 'note': ('picked ' + ', '.join(_name(names, i) for i in p['picked'])) if p['picked'] else
                         'no motif picked'} for p in passes]),
        'kept': pick([{**e, 'note': '✓ ' + _name(names, e['id'])} for e in dec
                      if e['s'] == 'decided' and e.get('act') == 'check' and e.get('kept') is True and not e.get('sure')]),
        'taken out': pick([{**e, 'note': '✕ ' + _name(names, e['id'])} for e in dec
                           if e['s'] == 'decided' and e.get('kept') is False and e.get('id')]),
        'not on its shortlist': pick(unshown),
        'new motif': pick(made),
        'passed as sure': pick([{**e, 'note': f"🎯 {_name(names, e['id'])} {round(100 * (e.get('fit') or 0))}%"} for e in dec
                                if e.get('sure')]),
        'refiled': pick(refiled),
        'split': pick(splits),
    }


def _known() -> dict[str, str]:
    """Claim key -> its words, for every claim anything here knows of"""
    index = _index()

    def make():
        from app.analysis import motif_index as mi
        out = {}
        for r in _shortlist_log():
            out[r.get('key') or mi.key(r.get('claim', ''))] = r.get('claim', '')
        for r in _refile_log():
            if r.get('key'):
                out[r['key']] = r.get('claim', '')
        for k, t in index.get('tellings', {}).items():
            out[k] = t.get('claim', '')
        for e in index['entries'].values():
            for c in e['claims']:
                out[mi.key(c['claim'])] = c['claim']
        return out
    from app.analysis import motif_index as mi, watch_list
    known = dict(_cached('known', (_index_stamp(), _stamp(mi.SHORTLIST_LOG, watch_list.REFILE_LOG)), make))
    for e in trace_events():
        if e.get('c'):
            known.setdefault(e['k'], e['c'])
    for e in _decided():
        known.setdefault(e['k'], e['c'])
    return known


def resolve(ref: str) -> tuple[str | None, str]:
    """(key, words) of the claim a reference names: its key, #id (a prefix of the key), or its words"""
    ref = (ref or '').strip()
    known = _known()
    if re.fullmatch(r'[0-9a-f]{16}', ref):
        return ref, known.get(ref, '')
    m = re.fullmatch(r'#?([0-9a-f]{4,16})', ref)
    if m:
        hits = sorted(k for k in known if k.startswith(m.group(1)))
        if hits:
            return hits[0], known[hits[0]]
    if not ref:
        return None, ''
    k = trace.key(ref)
    from app.analysis import motif_index as mi
    k2 = trace.key(mi.corrected(ref, _index()))
    return (k2 if k2 in known else k), known.get(k2) or known.get(k) or ref


def search(q: str, n: int = 30) -> list[dict]:
    q = (q or '').strip()
    known = _known()
    m = re.fullmatch(r'#([0-9a-f]{2,16})', q.lower())
    if m:
        hits = [k for k in known if k.startswith(m.group(1))]
    else:
        words = q.lower().split()
        hits = [k for k, c in known.items() if words and all(w in c.lower() for w in words)]
    return [{'k': k, 'c': known[k][:TEXT]} for k in hits[:n]]


# ---------- one claim's journey ----------

def _claim_detail(text: str) -> dict:
    """Where the claim came from, as the checker's claim panel reads it (scripts/validate.py's claim_detail)"""
    fn = getattr(sys.modules.get('__main__'), 'claim_detail', None)
    if fn is None:
        v = sys.modules.get('validate')
        if v is None:
            import importlib.util
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'scripts', 'validate.py')
            spec = importlib.util.spec_from_file_location('validate', path)
            v = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(v)
            sys.modules['validate'] = v
        fn = v.claim_detail
    return fn(text)


def source_of(text: str) -> dict:
    """claim_detail's answer, cut to what a card shows: a few posts, the fact-check's opening, a few tellings"""
    try:
        d = _claim_detail(text)
    except Exception as e:  # noqa: BLE001 - the journey stands without it
        return {'error': str(e)[:200]}
    keep = {k: d.get(k) for k in ('kind', 'source', 'title', 'url', 'published', 'summary', 'made', 'people', 'posts',
                                  'quote', 'side', 'model_words') if d.get(k) not in (None, '', [])}
    if d.get('examples'):
        keep['examples'] = [str(x)[:300] for x in d['examples'][:4]]
    if d.get('piece'):
        keep['piece'] = d['piece'][:700]
    if isinstance(d.get('context'), str):
        keep['context'] = d['context'][:700]
    if d.get('tellings'):
        keep['tellings'] = [{k: t.get(k) for k in ('show', 'quote', 'speaker', 'date', 'url') if t.get(k)}
                            for t in d['tellings'][:4] if isinstance(t, dict)]
    lab = d.get('label') or {}
    if isinstance(lab, dict) and lab:
        keep['label'] = {k: lab[k] for k in ('genre', 'motif', 'context', 'side') if lab.get(k)}
    if d.get('articles'):
        keep['articles'] = [a.get('title') for a in d['articles'][:3] if isinstance(a, dict) and a.get('title')]
    return keep


def _grid(e: dict, picked: set, verdict: dict) -> dict:
    """A traced shortlist with each signal's push on each motif: (value - mean) / spread × weight"""
    mu, sd, coef = e.get('mu') or [], e.get('sd') or [], e.get('coef') or []
    rows = []
    for r in e.get('rows') or []:
        x = r.get('x')
        row = {k: r.get(k) for k in ('id', 'why', 'rank', 'score')}
        if x and len(x) == len(coef) == len(mu) == len(sd):
            z = [(v - m) / (s or 1) for v, m, s in zip(x, mu, sd)]
            row.update(x=x, z=[round(v, 3) for v in z], push=[round(v * w, 3) for v, w in zip(z, coef)])
        row['picked'] = r.get('id') in picked
        if r.get('id') in verdict:
            row['verdict'] = verdict[r['id']]
        rows.append(row)
    return {**{k: e.get(k) for k in ('t', 'method', 'features', 'coef', 'bias', 'of', 'next', 'shown', 'seeds', 'refile',
                                      'source', 'ref', 'split_from', 'next_motif')}, 'rows': rows, 'traced': True}


def _pushes(e: dict) -> list[dict]:
    """A traced scoring, each filing with every feature's push (value × weight), largest first"""
    out = []
    fs, w = e.get('features') or [], e.get('w') or []
    for i, eid in enumerate(e.get('ids') or []):
        x = (e.get('x') or [])[i] if i < len(e.get('x') or []) else []
        pushes = sorted(({'f': f, 'v': v, 'w': wt, 'c': round(v * wt, 3)} for f, v, wt in zip(fs, x, w)),
                        key=lambda p: -abs(p['c']))
        out.append({'id': eid, 'fit': (e.get('fit') or [None] * (i + 1))[i], 'z': (e.get('z') or [None] * (i + 1))[i],
                    'bias': e.get('bias'), 'pushes': pushes})
    return out


def journey(ref: str) -> dict:
    from app.analysis import filing_confidence as fc
    from app.analysis import motif_index as mi
    from app.analysis import motif_signals as ms
    k, text = resolve(ref)
    if not k:
        return {'error': 'no claim named'}
    index = _index()
    names = _names(index)
    words = mi.originals(text, index) if text else set()
    keys = {k} | {mi.key(w) for w in words}
    tr = [e for e in trace_events() if e.get('k') in keys]
    dec = [e for e in _decided() if e['k'] in keys]
    by = defaultdict(list)
    for e in tr:
        by[e['s']].append(e)

    # where it came from
    written = {'traced': by['written'], 'source': source_of(text) if text else {}}
    # its shape and layers
    shapes = _json(ms.SHAPES, {})
    layered = _json(ms.LAYERED, {})
    shaped = {'shape': next((shapes[x] for x in keys if x in shapes), None),
              'layers': next((layered[x] for x in keys if x in layered), None), 'traced': bool(by['shaped'])}
    # every filing pass: traced, or as the shortlist and refile logs kept it
    verdict = {}
    for e in dec:
        if e.get('id') and e.get('kept') is not None:
            verdict[e['id']] = e['kept']
    passes = []
    picks = sorted(by['picked'] + by['refiled'], key=lambda e: e['t'])
    for e in sorted(by['shortlist'], key=lambda e: e['t']):
        p = next((x for x in picks if x['t'] >= e['t'] and bool(x['s'] == 'refiled') == bool(e.get('refile'))), {})
        if p:
            picks.remove(p)
        passes.append({'shortlist': _grid(e, set(p.get('picked') or []), verdict),
                       'picked': {k2: p.get(k2) for k2 in ('t', 'picked', 'new', 'reason', 'new_reason', 'filed', 'made',
                                                           'outcome', 'was', 'why')} if p else None})
    # a pass the trace has: its log rows are written moments after (the shortlist log once the model has answered)
    traced_at = [dt.fromisoformat(e['t']) for e in by['shortlist'] + by['picked'] + by['refiled']]

    def traced(at: str) -> bool:
        try:
            when = dt.fromisoformat(at)
        except (TypeError, ValueError):
            return False
        return any(abs((when - t).total_seconds()) <= 300 for t in traced_at)
    for r in _shortlist_log():
        if r.get('key') in keys and not traced(r.get('at')):
            passes.append({'shortlist': {'t': r['at'], 'shown': r.get('shown') or [], 'seeds': r.get('seeds') or [],
                                         'source': r.get('source'), 'next_motif': r.get('next'), 'traced': False,
                                         'rows': [{'id': i, 'picked': i in (r.get('picked') or []),
                                                   **({'verdict': verdict[i]} if i in verdict else {})} for i in r.get('shown') or []]},
                           'picked': {'t': r['at'], 'picked': r.get('picked') or [], 'new': r.get('new') or []}})
    for r in _refile_log():
        if r.get('key') in keys and not traced(r.get('at')):
            passes.append({'shortlist': {'t': r['at'], 'shown': r.get('shown') or [], 'refile': r.get('why'), 'traced': False,
                                         'source': r.get('source'),
                                         'rows': [{'id': i, 'picked': i in (r.get('picked') or []),
                                                   **({'verdict': verdict[i]} if i in verdict else {})} for i in r.get('shown') or []]},
                           'picked': {'t': r['at'], 'picked': r.get('picked') or [], 'new': r.get('new') or [],
                                      'filed': r.get('filed'), 'was': r.get('was'), 'why': r.get('why')}})
    passes.sort(key=lambda p: p['shortlist']['t'])
    # the confidence model's fits: traced, and the fit each filing has now
    now = []
    for e in mi.live(index):
        for c in e['claims']:
            if mi.key(c['claim']) in keys:
                now.append({'id': e['id'], 'fit': c.get('fit'), 'model': c.get('fit_model'), 'checked': c.get('checked'),
                            'rechecked': c.get('rechecked'), 'date': c.get('date'), 'refiled': c.get('refiled'),
                            'story': c.get('story'), 'story_tie': c.get('story_tie'), 'carrying': c.get('carrying'),
                            'variants': len(c.get('variants') or []), 'split_from': c.get('split_from'),
                            'yours': 'done' in e})
    alt = (_json(fc.ALTERNATIVES, {}).get(k) or {}).get('motifs') or []
    scored = {'traced': [{'t': e['t'], 'model': e.get('model'), 'sure_at': e.get('sure_at'), 'confirmed': e.get('confirmed'),
                          'filings': _pushes(e)} for e in sorted(by['scored'], key=lambda e: e['t'])],
              'now': now, 'alternatives': [{'id': i, 'fit': f} for i, f in alt],
              'sure_at': ((_json(fc.MODEL, {}) or {}).get('test') or {}).get('sure_at')}
    # splits: the telling it was split into, the one it was split from, the organizer's reading
    split = {'proposed': by['split_proposed']}
    t = next((index['tellings'][x] for x in keys if x in index.get('tellings', {})), None)
    if t:
        split['children'] = [{'k': mi.key(c), 'c': c} for c in t.get('children', [])]
        split.update({f: t.get(f) for f in ('at', 'by', 'why')})
        split['was_in'] = [f.get('id') for f in t.get('filings', [])]
    parent = next((x['split_from'] for x in now if x.get('split_from')), None)
    if parent:
        split['from'] = {'k': mi.key(parent), 'c': parent}
    # downstream: the story it was told about, its motifs' occasions
    motifs = {}
    for x in now:
        e = index['entries'][x['id']]
        motifs[x['id']] = {'name': e['name'], 'genre': mi.genre_of(e), 'told': e.get('told'), 'size': len(e['claims']),
                           'yours': 'done' in e, 'note': (e.get('note') or '')[:300]}
    stories = {}
    ids = {x['story'] for x in now if isinstance(x.get('story'), int)}
    if ids:
        try:
            from app.analysis import flow
            stories = {str(i): r for i, r in flow.story_rows(ids).items()}
        except Exception:  # noqa: BLE001 - the ids alone will do
            pass
    for x in [i for p in passes for r in p['shortlist'].get('rows', []) for i in [r['id']]] + \
            [i for p in passes for i in (p['picked'] or {}).get('filed') or []] + [e.get('id') for e in dec] + \
            [a['id'] for a in scored['alternatives']] + [n['id'] for p in passes for n in p['shortlist'].get('next') or []]:
        if x and x in names and x not in motifs:
            motifs[x] = {'name': names[x]['name'], 'genre': names[x]['genre']}
    logged = next((p['shortlist'].get('source') for p in passes if p['shortlist'].get('source')), None) or \
        next((f.get('source') for f in (t or {}).get('filings', []) if f.get('source')), None)
    return {'claim': {'k': k, 'id6': k[:6], 'c': text, 'words': sorted(words - {text}), 'keys': sorted(keys)},
            'logged_source': logged,
            'written': written, 'shaped': shaped, 'passes': passes, 'scored': scored, 'decided': dec,
            'split': split, 'motifs': motifs, 'stories': stories, 'glossary': {g: list(v) for g, v in GLOSSARY.items()},
            'traced': bool(tr), 'traced_since': _traced_since()}


def _traced_since() -> str | None:
    first = sorted(glob.glob(os.path.join(trace.folder(), '*.jsonl')))
    return os.path.basename(first[0])[:10] if first else None


def view(params: dict) -> dict:
    try:
        if params.get('claim'):
            return journey(params['claim'])
        if params.get('q'):
            return {'found': search(params['q'])}
        return stream(params)
    except Exception as e:  # noqa: BLE001 - the page says what went wrong, the checker stays up
        logger.exception("Live view")
        return {'error': f'{type(e).__name__}: {e}'[:300]}
