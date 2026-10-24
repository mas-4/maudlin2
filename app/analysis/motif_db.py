"""The motif index in SQLite (Oct 21; the person: "the index is 1.1mb json? that's way too fucking big. it should be
sqlite"). Until then the whole index was one JSON file, read whole and written whole on every change, with a copy of
the whole file kept for every save (250-370 a day, 1.4 GB in curation.sqlite) and for each of the last 50 undo steps.

The code still works on the index as a dict (motif_index.load and save): a save writes only the rows that changed,
in one transaction, and logs each changed row's old and new value. That log is the index's history, and what undo
takes back.

    motifs    one row a motif: id, its order, name, merged_into, and the rest of the entry (JSON)
    filings   a motif's claims in order: motif, n, the claim's key and text, and the rest of the filing (JSON)
    parts     every other part of the index, a row an item: the claims map (claim key -> motif ids), corrections,
              groups, related notes, tellings, held claims, the facet values and notes, the next id; the lists
              (not_same, related) keyed by position
    changes   every row each save changed: txn (the save), when, table, key, old and new (JSON; null: none)
    meta      txn (the last save's number), parts (the index's parts in order, with their kinds)

To read it by hand: sqlite3 data/motif_index.sqlite "select name, json_extract(data, '$.note') from motifs where
merged_into is null". The index was moved in by `python -m app.analysis.motif_db migrate`."""
import json
import os
import sqlite3
import sys
from datetime import datetime as dt

SCHEMA = """
CREATE TABLE IF NOT EXISTS motifs (id TEXT PRIMARY KEY, n INTEGER NOT NULL, name TEXT, merged_into TEXT,
                                   data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS filings (motif TEXT NOT NULL, n INTEGER NOT NULL, claim_key TEXT, claim TEXT,
                                    data TEXT NOT NULL, PRIMARY KEY (motif, n));
CREATE INDEX IF NOT EXISTS filings_claim ON filings (claim_key);
CREATE TABLE IF NOT EXISTS parts (part TEXT NOT NULL, key TEXT NOT NULL, n INTEGER NOT NULL, value TEXT NOT NULL,
                                  PRIMARY KEY (part, key));
CREATE TABLE IF NOT EXISTS changes (id INTEGER PRIMARY KEY, txn INTEGER NOT NULL, at TEXT NOT NULL, tbl TEXT NOT NULL,
                                    key TEXT NOT NULL, old TEXT, new TEXT);
CREATE INDEX IF NOT EXISTS changes_txn ON changes (txn);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
EMPTY = {'next': 1, 'entries': {}, 'claims': {}}
COLUMNS = {'motifs': ('id', 'n', 'name', 'merged_into', 'data'),
           'filings': ('motif', 'n', 'claim_key', 'claim', 'data'),
           'parts': ('part', 'key', 'n', 'value')}


def dumps(v) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(',', ':'))


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path, timeout=60, isolation_level=None)  # transactions begun by hand (BEGIN IMMEDIATE)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA synchronous=NORMAL')
    con.executescript(SCHEMA)
    return con


def _key(claim: str) -> str:
    from app.analysis.motif_index import key
    return key(claim)


def rows(index: dict) -> dict[str, dict[str, tuple]]:
    """The index as rows: {table: {row key: row}}, and the parts' order and kinds (meta 'parts')"""
    out = {'motifs': {}, 'filings': {}, 'parts': {}}
    kinds = []
    for part, value in index.items():
        if part == 'entries':
            kinds.append([part, 'entries'])
            for n, (eid, e) in enumerate(value.items()):
                name, merged = e.get('name'), e.get('merged_into')  # in their own columns, not again in data
                rest = {k: v for k, v in e.items() if k != 'claims' and not (k == 'name' and isinstance(name, str))
                        and not (k == 'merged_into' and isinstance(merged, str))}
                out['motifs'][eid] = (eid, n, name if isinstance(name, str) else None,
                                      merged if isinstance(merged, str) else None, dumps(rest))
                for i, c in enumerate(e.get('claims', [])):
                    text = c.get('claim') if isinstance(c, dict) else None
                    record = {k: v for k, v in c.items() if k != 'claim'} if isinstance(text, str) else c
                    out['filings'][f'{eid}\t{i}'] = (eid, i, _key(text) if isinstance(text, str) else None,
                                                    text if isinstance(text, str) else None, dumps(record))
        elif isinstance(value, dict):
            kinds.append([part, 'dict'])
            for n, (k, v) in enumerate(value.items()):
                out['parts'][f'{part}\t{k}'] = (part, str(k), n, dumps(v))
        elif isinstance(value, list):
            kinds.append([part, 'list'])
            for n, v in enumerate(value):
                out['parts'][f'{part}\t{n}'] = (part, str(n), n, dumps(v))
        else:
            kinds.append([part, 'value'])
            out['parts'][f'{part}\t'] = (part, '', 0, dumps(value))
    return out | {'meta': {'parts': dumps(kinds)}}


def _key_of(table: str, row: tuple) -> str:
    return row[0] if table == 'motifs' else f'{row[0]}\t{row[1]}'


def _current(con: sqlite3.Connection) -> dict[str, dict[str, tuple]]:
    out = {t: {_key_of(t, r): tuple(r) for r in con.execute(f"SELECT {', '.join(cols)} FROM {t}")}
           for t, cols in COLUMNS.items()}
    out['meta'] = dict(con.execute("SELECT key, value FROM meta WHERE key = 'parts'"))
    return out


def index_of(r: dict[str, dict[str, tuple]]) -> dict:
    """rows() turned back into the index"""
    kinds = json.loads(r['meta'].get('parts') or '[]') or [['next', 'value'], ['entries', 'entries'], ['claims', 'dict']]
    claims = {}
    for motif, _n, _k, text, data in sorted(r['filings'].values(), key=lambda x: (x[0], x[1])):
        record = json.loads(data)
        claims.setdefault(motif, []).append({'claim': text, **record} if text is not None else record)
    by_part = {}
    for part, key, _n, value in sorted(r['parts'].values(), key=lambda x: (x[0], x[2])):
        by_part.setdefault(part, []).append((key, value))
    index = {}
    for part, kind in kinds:
        if kind == 'entries':
            index[part] = {eid: {**({'id': eid} if 'id' in (d := json.loads(data)) else {}),
                                 **({'name': name} if name is not None else {}), **d,
                                 **({'merged_into': merged} if merged is not None else {}),
                                 'claims': claims.get(eid, [])}
                           for eid, _n, name, merged, data in sorted(r['motifs'].values(), key=lambda x: x[1])}
        elif kind == 'dict':
            index[part] = {k: json.loads(v) for k, v in by_part.get(part, [])}
        elif kind == 'list':
            index[part] = [json.loads(v) for _k, v in by_part.get(part, [])]
        else:
            got = by_part.get(part)
            if got:
                index[part] = json.loads(got[0][1])
    return index


def read(path: str) -> dict:
    """The index, or an empty one when there's no file yet (none is made by reading)"""
    if not os.path.exists(path):
        return json.loads(json.dumps(EMPTY))
    con = connect(path)
    try:
        con.execute('BEGIN')  # one consistent view across the tables
        r = _current(con)
        con.execute('COMMIT')
    finally:
        con.close()
    return index_of(r) if r['motifs'] or r['parts'] else json.loads(json.dumps(EMPTY))


def txn(path: str) -> int:
    """The last save's number: 0 before the first. Changes whenever the index does, so it serves as a cache's stamp"""
    if not os.path.exists(path):
        return 0
    con = connect(path)
    try:
        got = con.execute("SELECT value FROM meta WHERE key = 'txn'").fetchone()
    finally:
        con.close()
    return int(got[0]) if got else 0


def _write_rows(con: sqlite3.Connection, new: dict, log: bool = True) -> int:
    """Make the tables hold `new`, inside the caller's transaction; the save's number (unchanged when nothing did)"""
    old = _current(con)
    t = int((con.execute("SELECT value FROM meta WHERE key = 'txn'").fetchone() or [0])[0])
    changed = []
    for table in COLUMNS:
        for k in old[table].keys() - new[table].keys():
            changed.append((table, k, old[table][k], None))
        for k, row in new[table].items():
            if old[table].get(k) != row:
                changed.append((table, k, old[table].get(k), row))
    parts_changed = old['meta'].get('parts') != new['meta']['parts']
    if not changed and not parts_changed:
        return t
    t += 1
    at = dt.now().isoformat(timespec='seconds')
    for table, k, before, after in changed:
        cols = COLUMNS[table]
        if after is None:
            if table == 'motifs':
                con.execute('DELETE FROM motifs WHERE id = ?', (k,))
            else:
                con.execute(f'DELETE FROM {table} WHERE {cols[0]} = ? AND {cols[1]} = ?', before[:2])
        else:
            con.execute(f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", after)
        if log:
            con.execute('INSERT INTO changes (txn, at, tbl, key, old, new) VALUES (?, ?, ?, ?, ?, ?)',
                        (t, at, table, k, dumps(list(before)) if before else None, dumps(list(after)) if after else None))
    if parts_changed:
        con.execute("INSERT OR REPLACE INTO meta VALUES ('parts', ?)", (new['meta']['parts'],))
        if log:
            con.execute('INSERT INTO changes (txn, at, tbl, key, old, new) VALUES (?, ?, ?, ?, ?, ?)',
                        (t, at, 'meta', 'parts', old['meta'].get('parts'), new['meta']['parts']))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('txn', ?)", (str(t),))
    return t


def write(path: str, index: dict, log: bool = True) -> int:
    """Save the index: only the rows that changed, in one transaction, each logged. The save's number"""
    new = rows(index)
    con = connect(path)
    try:
        con.execute('BEGIN IMMEDIATE')
        try:
            t = _write_rows(con, new, log)
            con.execute('COMMIT')
        except BaseException:
            con.execute('ROLLBACK')
            raise
    finally:
        con.close()
    return t


def last_origin(path: str, keys: set[str]) -> dict:
    """Where a claim last came from (its newest filing row with a source), by any of its keys: a claim taken out of
    every motif keeps no row of its own, so one filed again by hand lost its posts and tellings (Oct 24, 77 filings)"""
    if not keys or not os.path.exists(path):
        return {}
    con = connect(path)
    try:
        for k in keys:
            for old, new in con.execute("SELECT old, new FROM changes WHERE tbl = 'filings' AND (new LIKE ? OR old LIKE ?)"
                                        ' ORDER BY id DESC', (f'%"{k}"%', f'%"{k}"%')):
                for row in (new, old):
                    if not row:
                        continue
                    r = json.loads(row)
                    data = json.loads(r[4]) if isinstance(r[4], str) else r[4]
                    if r[2] == k and (data.get('source') or data.get('ref')):
                        return {f: data[f] for f in ('source', 'ref', 'side', 'split_from') if data.get(f) is not None}
    finally:
        con.close()
    return {}


def state_at(path: str, at_txn: int) -> dict:
    """The index as it was after save `at_txn`: today's rows with every later change taken back, newest first"""
    con = connect(path)
    try:
        con.execute('BEGIN')
        r = _current(con)
        later = con.execute('SELECT tbl, key, old FROM changes WHERE txn > ? ORDER BY id DESC', (at_txn,)).fetchall()
        con.execute('COMMIT')
    finally:
        con.close()
    for table, k, before in later:
        if table == 'meta':
            r['meta'][k] = before
        elif before is None:
            r[table].pop(k, None)
        else:
            r[table][k] = tuple(json.loads(before))
    return index_of(r)


def reads_as(path: str, txn: int) -> bool:
    """Whether the index reads now as save `txn` left it, whatever saves came between (an undo putting it back is a save
    of its own: Oct 22, the checker's second undo in a row was refused, as if the index had changed since)"""
    return canonical(read(path)) == canonical(state_at(path, txn))


def revert(path: str, to_txn: int) -> int:
    """Put the index back as it was after save `to_txn`, as a new save of its own (so it can be taken back too)"""
    return write(path, state_at(path, to_txn))


def migrate(json_path: str, db_path: str) -> dict:
    """The JSON index moved into a new database, checked to read back the same, and the JSON file renamed aside"""
    if os.path.exists(db_path):
        raise ValueError(f'{db_path} exists already')
    with open(json_path) as f:
        index = json.load(f)
    tmp = db_path + '.migrating'
    for side in ('', '-wal', '-shm'):
        if os.path.exists(tmp + side):
            os.remove(tmp + side)
    con = connect(tmp)
    try:
        con.execute('BEGIN IMMEDIATE')
        _write_rows(con, rows(index), log=False)
        con.execute("INSERT OR REPLACE INTO meta VALUES ('migrated', ?)",
                    (dumps({'from': os.path.basename(json_path), 'at': dt.now().isoformat(timespec='seconds'),
                            'bytes': os.path.getsize(json_path)}),))
        con.execute('COMMIT')
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    finally:
        con.close()
    back = read(tmp)
    if canonical(back) != canonical(index):
        raise ValueError('the database does not read back as the JSON index: nothing moved')
    os.replace(tmp, db_path)
    for side in ('-wal', '-shm'):
        if os.path.exists(tmp + side):
            os.remove(tmp + side)
    aside = f"{json_path}.migrated-{dt.now().strftime('%Y-%m-%d')}"
    os.replace(json_path, aside)
    e = index.get('entries', {})
    return {'motifs': len(e), 'filings': sum(len(x.get('claims', [])) for x in e.values()),
            'json MB': round(os.path.getsize(aside) / 1e6, 2), 'sqlite MB': round(os.path.getsize(db_path) / 1e6, 2),
            'json kept as': aside}


def canonical(index: dict) -> str:
    """The index as sorted JSON: the same text for the same content, whatever the order of keys inside an entry"""
    return json.dumps(index, sort_keys=True, ensure_ascii=False)


if __name__ == '__main__':
    if sys.argv[1:2] == ['migrate']:
        from app.analysis import motif_index as mi
        print(mi.migrate())
    else:
        print('usage: python -m app.analysis.motif_db migrate')
