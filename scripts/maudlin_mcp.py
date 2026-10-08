"""An MCP server for working with the project's data from Claude Code, read-only: the site's database (SQLite, opened
in read-only mode, so nothing can be written even by mistake) and the motif index (through app/analysis/motif_index.py,
the code the checker uses); and changes to the index, only through the checker's own actions (checker_action), so
each is validated, logged in the curation log marked by Claude, and undoable.

Registered in .mcp.json; runs over stdio:
    .venv/bin/python scripts/maudlin_mcp.py
"""
import json
import logging
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# stdout carries the protocol: the app's console logging goes to stderr instead
import app.utils.logger as _logger  # noqa: E402

_console = _logger._get_console_handler


def _to_stderr():
    handler = _console()
    handler.setStream(sys.stderr)
    return handler


_logger._get_console_handler = _to_stderr

from mcp.server.mcpserver import MCPServer  # noqa: E402

from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402
from app.utils import Config  # noqa: E402

logging.getLogger().handlers = [h for h in logging.getLogger().handlers if getattr(h, 'stream', None) is not sys.stdout]

DB = os.path.join(Config.data, 'data.db') if os.path.exists(os.path.join(Config.data, 'data.db')) else \
    Config.connection_string.removeprefix('sqlite:///')
ROWS = 200  # rows a query returns, at most
CELL = 600  # characters of a text cell shown

server = MCPServer('maudlin', instructions=(
    "Read-only access to bignews.day's data. db_schema and db_query read the site's SQLite database (headlines, "
    "articles, agencies, stories, side feeds and their transcripts...). The motif_* tools read the motif index: motifs "
    "(rumor and narrative shapes) with their claims, genre (a layer of story: Archetypes, Plots, Theories...), groups "
    "(a separate axis), rests-on links (the only hierarchy: a motif only makes sense given the one it rests on, a kind of it or a case, argument or figure that tells it; across genres too) and related links. checker_action makes a "
    "change the person asked for through the checker (logged, undoable, marked by Claude); checker_undo takes back "
    "Claude's own last change only. check_queue, second_look, unfiled_claims and claim_detail show the person's "
    "work queues and where a claim came from."))


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True, timeout=10)
    con.execute('PRAGMA query_only = ON')
    return con


def _cell(v):
    if isinstance(v, bytes):
        return f'<{len(v)} bytes>'
    if isinstance(v, str) and len(v) > CELL:
        return v[:CELL] + f'… ({len(v)} chars)'
    return v


@server.tool()
def db_schema(table: str = '') -> str:
    """The database's tables with their row counts, or one table's columns (name, type) and indexes."""
    with _connect() as con:
        if not table:
            names = [r[0] for r in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name")]
            return '\n'.join(f'{n}: {con.execute(f"select count(*) from {n}").fetchone()[0]} rows' for n in names)
        if not re.fullmatch(r'\w+', table):
            return 'no such table'
        cols = con.execute(f'pragma table_info({table})').fetchall()
        if not cols:
            return 'no such table'
        idx = [r[1] for r in con.execute(f'pragma index_list({table})')]
        return '\n'.join(f'{c[1]} {c[2]}{" primary key" if c[5] else ""}' for c in cols) + (f'\nindexes: {", ".join(idx)}' if idx else '')


@server.tool()
def db_query(sql: str, limit: int = 50) -> str:
    """Run one read-only SQL query (SELECT or WITH) on the site's database; at most `limit` rows (up to 200), long
    text cut. The connection is read-only: writes fail."""
    if not re.match(r'\s*(select|with|pragma\s+table_info|explain)\b', sql, re.I):
        return 'read-only: a SELECT or WITH query, please'
    limit = max(1, min(int(limit), ROWS))
    with _connect() as con:
        try:
            cur = con.execute(sql)
        except sqlite3.Error as e:
            return f'error: {e}'
        cols = [d[0] for d in cur.description or []]
        rows = cur.fetchmany(limit + 1)
    out = {'columns': cols, 'rows': [[_cell(v) for v in r] for r in rows[:limit]]}
    if len(rows) > limit:
        out['more'] = f'more rows: only the first {limit} shown'
    return json.dumps(out, ensure_ascii=False, default=str)


def _brief(e: dict, index: dict) -> dict:
    names = {gid: g['name'] for gid, g in index.get('groups', {}).items()}
    return {'id': e['id'], 'name': e['name'], 'claims': len(e['claims']), 'genre': mi.genre_of(e),
            'groups': [names.get(g, g) for g in mi.groups_of(e)], 'done': mi.public(e), 'note': (e.get('note') or '')[:200],
            **({'drafted by the model': {k: [names.get(g, g) for g in v] if k == 'groups' else v
                                         for k, v in e['by_model'].items()}} if e.get('by_model') else {})}


@server.tool()
def motif_search(query: str = '', genre: str = '', group: str = '', limit: int = 30) -> str:
    """Motifs whose name, note or id has every word of `query` (all motifs if empty), optionally of one genre or in
    one group (by name), biggest first."""
    index = mi.load()
    groups = {g['name'].lower(): gid for gid, g in index.get('groups', {}).items()}
    words = query.lower().split()
    out = []
    for e in mi.live(index):
        hay = f"{e['id']} {e['name']} {e.get('note') or ''}".lower()
        if words and not all(w in hay for w in words):
            continue
        if genre and (mi.genre_of(e) or '').lower() != genre.lower():
            continue
        if group and groups.get(group.lower()) not in mi.groups_of(e):
            continue
        out.append(e)
    out.sort(key=lambda e: -len(e['claims']))
    return json.dumps({'found': len(out), 'motifs': [_brief(e, index) for e in out[:max(1, min(limit, 200))]]}, ensure_ascii=False)


@server.tool()
def motif(motif_id: str) -> str:
    """One motif in full: name, note, genre, groups (by name), done or not, what it rests on and what rests on it, related
    motifs, the motifs it shares claims with (co-occurrence, not relatedness), and every claim with its source and
    whether a person checked it."""
    index = mi.load()
    try:
        eid = mi.resolve(index, motif_id.strip().upper())
    except Exception:
        return 'no such motif'
    e = index['entries'].get(eid)
    if not e:
        return 'no such motif'
    name = lambda i: f"{index['entries'][i]['name']} ({i})" if i in index['entries'] else i  # noqa: E731
    live = mi.live(index)
    shared = {}
    keys = {mi.key(c['claim']) for c in e['claims']}
    for o in live:
        if o['id'] != eid:
            n = sum(1 for c in o['claims'] if mi.key(c['claim']) in keys)
            if n:
                shared[name(o['id'])] = n
    return json.dumps({
        **_brief(e, index), 'note': e.get('note') or '',
        'merged_into': e.get('merged_into'), 'first_seen': e.get('first_seen'),
        'rests on': [name(p) for p in mi.parents_of(e)],
        'rest on it': [name(o['id']) for o in live if eid in mi.parents_of(o)],
        'related': [name(x) for p in index.get('related', []) if eid in p for x in p if x != eid],
        'shares claims with': dict(sorted(shared.items(), key=lambda kv: -kv[1])),
        'claims': [{'claim': c['claim'], 'source': c.get('source'), 'checked': c.get('checked'), 'date': c.get('date')}
                   for c in e['claims']]}, ensure_ascii=False)


@server.tool()
def motif_claims(query: str, limit: int = 30) -> str:
    """Claims containing every word of `query`, each with the motifs it's filed under."""
    index = mi.load()
    words = query.lower().split()
    found = {}
    for e in mi.live(index):
        for c in e['claims']:
            if all(w in c['claim'].lower() for w in words):
                f = found.setdefault(mi.key(c['claim']), {'claim': c['claim'], 'source': c.get('source'), 'motifs': []})
                f['motifs'].append(f"{e['name']} ({e['id']}){' ✓' if c.get('checked') == 'yes' else ''}")
    rows = list(found.values())
    return json.dumps({'found': len(rows), 'claims': rows[:max(1, min(limit, 200))]}, ensure_ascii=False)


@server.tool()
def check_queue(limit: int = 30) -> str:
    """The filings waiting for the person's check, as the workbench's ✅ check tab shows them: claim by claim, the
    likeliest first, each motif with its note and fit (the chance the person keeps it, from the confidence model;
    none until the hourly run has scored it). Verdicts go through checker_action ({'action': 'check', 'claim', 'id',
    'answer': 'yes'|'no'}), and only when the person asks."""
    V = _validate()
    index = mi.load()
    claims = {}
    for x in V.check_queue():
        c = claims.setdefault(x['claim'], {'claim': x['claim'], 'source': x.get('source'), 'motifs': []})
        e = index['entries'].get(x['id'], {})
        c['motifs'].append({'id': x['id'], 'name': x['name'], 'note': e.get('note'), 'fit': x.get('fit'),
                            'can_be_sure': x.get('can_be_sure')})
    rows = list(claims.values())
    return json.dumps({'claims waiting': len(rows), 'filings': sum(len(r['motifs']) for r in rows),
                       'claims': rows[:max(1, min(limit, 200))]}, ensure_ascii=False)


@server.tool()
def second_look() -> str:
    """The person's confirmed filings the confidence model finds least likely (the workbench's 🔁 second look):
    possible honest slips, the least likely first, each with its motif's note."""
    V = _validate()
    index = mi.load()
    return json.dumps([{**r, 'note': index['entries'].get(r['id'], {}).get('note')} for r in V.second_look()],
                      ensure_ascii=False)


@server.tool()
def unfiled_claims(query: str = '', limit: int = 30) -> str:
    """Claims waiting with no motif (from the latest folklore report, recent fact-checks, the shows and focus groups),
    with every word of `query` if given: what the person might file by hand."""
    words = query.lower().split()
    rows = [c for c in mi.searchable_claims() if not c.get('motifs') and all(w in c['claim'].lower() for w in words)]
    return json.dumps({'found': len(rows), 'claims': [{'claim': c['claim'], 'source': c.get('source'), 'ref': c.get('ref')}
                                                      for c in rows[:max(1, min(limit, 200))]]}, ensure_ascii=False)


@server.tool()
def claim_detail(claim: str) -> str:
    """Where a claim came from, as the workbench's 'where it came from' shows it: the fact-check, the posts that told
    it, the focus group, or every telling on the shows (show, episode, speaker, transcript). The claim's exact words."""
    return json.dumps(_validate().claim_detail(claim), ensure_ascii=False, default=str)


@server.tool()
def motif_overview() -> str:
    """The index in numbers, and its groups and genres with their sizes."""
    index = mi.load()
    live = mi.live(index)
    groups = {gid: g['name'] for gid, g in index.get('groups', {}).items()}
    by_group, by_genre = {}, {}
    for e in live:
        for g in mi.groups_of(e):
            by_group[groups.get(g, g)] = by_group.get(groups.get(g, g), 0) + 1
        by_genre[mi.genre_of(e) or '(none)'] = by_genre.get(mi.genre_of(e) or '(none)', 0) + 1
    return json.dumps({
        'motifs': len(live), 'done': sum(1 for e in live if mi.public(e)),
        'claims': len({mi.key(c['claim']) for e in live for c in e['claims']}),
        'filings': sum(len(e['claims']) for e in live),
        'unchecked filings': sum(1 for e in live for c in e['claims'] if not c.get('checked')),
        'rests-on links': sum(len(mi.parents_of(e)) for e in live), 'related pairs': len(index.get('related', [])),
        'groups': dict(sorted(by_group.items())), 'genres': dict(sorted(by_genre.items()))}, ensure_ascii=False)


@server.tool()
def motif_proposals(kind: str = '', limit: int = 50) -> str:
    """The open proposals of the correction proposer (as the workbench's 💡 tab lists them, best fit first), optionally
    of one kind (rename, note, merge, unparent, unrelate, parent, relate, group, genre)."""
    index = mi.load()
    name = lambda i: index['entries'][i]['name'] if i in index['entries'] else i  # noqa: E731
    out = []
    for p in mp.open_proposals():
        if kind and p['kind'] != kind:
            continue
        args = {k: (f'{name(v)} ({v})' if isinstance(v, str) and re.fullmatch(r'M\d+', v) else v) for k, v in p['args'].items()}
        out.append({'id': p['id'], 'kind': p['kind'], 'args': args, 'reason': p.get('reason'), 'fit': p.get('fit'),
                    'unlikely': p.get('unlikely'), 'judge': (p.get('judge') or {}).get('score')})
    return json.dumps({'open': len(out), 'proposals': out[:max(1, min(limit, 300))]}, ensure_ascii=False)


# ---------- changes, through the checker (logged, undoable, marked by Claude) ----------
CHECKER = 'http://localhost:8766'


def _post(path: str, body: dict) -> tuple[int, str]:
    import urllib.error
    import urllib.request
    req = urllib.request.Request(CHECKER + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except OSError as e:
        return 0, f'the checker (port 8766) isn\'t running: {e}'


@server.tool()
def checker_action(action: dict) -> str:
    """Make one change to the motif index through the checker, exactly as the person's clicks do: validated, written
    to the curation log marked by Claude, and on the undo stack labelled "(by Claude)". Only when the person asked for
    the change. An action is a dict with "action" and its fields, e.g.:
      rename {id, name} · note {id, note} · done {id} (mark done / unmark) · delete {id}
      merge {source, target} (source folds into target) · parent {id, parent, on: true|false} (id rests on parent)
      relate / unrelate {a, b} · not_same {a, b}
      group_member {id, group, on} · group_assign {id, group|null} · group_new {name, id?} · group_rename {group, name}
      facet {id, facet: "genre", value|null} · facet_value {facet: "genre", value}
      also {claim, source, target} (file it there too) · move {claim, source, target} · unfile {claim, id}
      check {claim, id, answer: yes|no|unsure} · no_motif {claim} · new_with {name, claims: [{claim, source?}]}
      batch {steps: [actions]} (one undo step)
    Motifs by id (M123), groups by id (G01; motif_overview and motif have names). Returns the checker's answer."""
    if not isinstance(action, dict) or not action.get('action'):
        return 'an action is a dict with "action"'
    status, text = _post('/workbench', {**action, 'by': 'claude'})
    if status == 200:
        return f'done: {action["action"]} (logged and undoable, by Claude)'
    return f'refused ({status}): {text}'


_V = None


def _validate():
    """The checker's own code (scripts/validate.py), for reading its undo stack"""
    global _V
    if _V is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location('validate', os.path.join(os.path.dirname(__file__), 'validate.py'))
        _V = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_V)
    return _V


@server.tool()
def checker_undo() -> str:
    """Undo Claude's own last change, only if it's the newest one on the undo stack (never the person's)."""
    found = _validate().last_undo()
    if not found:
        return 'nothing to undo'
    what = found[1].get('what', '')
    if not what.endswith('(by Claude)'):
        return f'the newest change is the person\'s, not Claude\'s ({what}): not undoing it'
    status, text = _post('/undo', {})
    return f'undid: {what}' if status == 200 else f'refused ({status}): {text}'


if __name__ == '__main__':
    server.run('stdio')
