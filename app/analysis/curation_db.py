"""The person's curation in a database of its own (Oct 8, the person: keep the training data in a database; let me save
a state and go back to it). maudlin-data/curation.sqlite, separate from data.db so the hourly scrape's writes never hold
up a save in the checker, and backed up with it.

  versions     every save of the motif index, compressed (motif_index.save): its whole history, not just the last 50
               undo steps
  checkpoints  a state the person saved by name (or one saved before a revert), to go back to: the motif index version
               and the proposals file as they were
  curation     the curation log (every change made in the checker, with what it touched before), mirrored from
               validation/curation_log.jsonl; a change undone by going back to a checkpoint is marked reverted, so the
               models stop learning from a decision the person took back

The JSON files stay the working copy for now; this keeps their history. Nothing here may stop a save: a failure is
logged and the save goes on."""
import contextlib
import hashlib
import json
import os
import sqlite3
import zlib
from datetime import datetime as dt
from datetime import timedelta as td

from app.utils import Config, get_logger

logger = get_logger(__name__)

DB = os.path.join(Config.data, 'curation.sqlite')
KEEP_ALL = td(days=7)  # every version this recent; older ones thinned to one an hour (checkpoints' versions kept)
SCHEMA = """
CREATE TABLE IF NOT EXISTS versions (id INTEGER PRIMARY KEY, at TEXT NOT NULL, sha TEXT NOT NULL, size INTEGER NOT NULL,
                                     data BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS versions_at ON versions (at);
CREATE TABLE IF NOT EXISTS checkpoints (id INTEGER PRIMARY KEY, at TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
                                        version INTEGER NOT NULL REFERENCES versions (id), proposals BLOB,
                                        log_id INTEGER NOT NULL DEFAULT 0, reverted_ids TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS curation (id INTEGER PRIMARY KEY, at TEXT NOT NULL, page TEXT, by TEXT, action TEXT NOT NULL,
                                     before TEXT, reverted INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS curation_at ON curation (at);
"""


@contextlib.contextmanager
def connect():
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, timeout=30)
    try:
        con.execute('PRAGMA journal_mode=WAL')
        con.executescript(SCHEMA)
        with con:
            yield con
    finally:
        con.close()


def now() -> str:
    return dt.now().isoformat(timespec='seconds')


def _pack(text: str) -> bytes:
    return zlib.compress(text.encode(), 6)


def _unpack(blob: bytes) -> str:
    return zlib.decompress(blob).decode()


def record_version(text: str) -> int | None:
    """Keep this state of the motif index (its JSON text) unless it's the same as the last one kept; its version id"""
    sha = hashlib.sha1(text.encode()).hexdigest()
    try:
        with connect() as con:
            last = con.execute('SELECT id, sha FROM versions ORDER BY id DESC LIMIT 1').fetchone()
            if last and last[1] == sha:
                return last[0]
            vid = con.execute('INSERT INTO versions (at, sha, size, data) VALUES (?, ?, ?, ?)',
                              (now(), sha, len(text), _pack(text))).lastrowid
        if vid % 500 == 0:
            thin()
        return vid
    except sqlite3.Error as e:
        logger.warning("Curation database: version not kept (%s)", e)
        return None


def record_action(at: str, page: str | None, action: dict, before: dict | None, by: str | None = None):
    try:
        with connect() as con:
            con.execute('INSERT INTO curation (at, page, by, action, before) VALUES (?, ?, ?, ?, ?)',
                        (at, page, by, json.dumps(action), json.dumps(before) if before is not None else None))
    except sqlite3.Error as e:
        logger.warning("Curation database: action not kept (%s)", e)


def backfill_log(path: str) -> int:
    """The curation log's lines not in the table yet (by time and action), oldest first"""
    with connect() as con:
        have = {(a, x) for a, x in con.execute('SELECT at, action FROM curation')}
        rows = []
        with open(path) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                act = json.dumps(r.get('action'))
                if (r.get('at'), act) not in have:
                    rows.append((r.get('at'), r.get('page'), r.get('by'), act,
                                 json.dumps(r.get('before')) if r.get('before') is not None else None))
        con.executemany('INSERT INTO curation (at, page, by, action, before) VALUES (?, ?, ?, ?, ?)', rows)
    return len(rows)


def actions(include_reverted: bool = False) -> list[dict]:
    """The curation log, oldest first: {'at', 'page', 'by', 'action', 'before'}"""
    with connect() as con:
        q = 'SELECT at, page, by, action, before FROM curation' + ('' if include_reverted else ' WHERE reverted = 0')
        return [{'at': a, 'page': p, 'by': b, 'action': json.loads(x), 'before': json.loads(y) if y else None}
                for a, p, b, x, y in con.execute(q + ' ORDER BY id')]


def checkpoint(name: str, index_text: str, proposals_text: str | None, kind: str = 'manual') -> dict:
    """Save the current state by name"""
    version = record_version(index_text)
    if version is None:
        raise ValueError("the curation database couldn't keep this state")
    with connect() as con:
        log_id = con.execute('SELECT COALESCE(MAX(id), 0) FROM curation').fetchone()[0]  # the changes it includes
        gone = [r[0] for r in con.execute('SELECT id FROM curation WHERE reverted = 1')]  # ...but those taken back
        cid = con.execute('INSERT INTO checkpoints (at, name, kind, version, proposals, log_id, reverted_ids) '
                          'VALUES (?, ?, ?, ?, ?, ?, ?)', (now(), name.strip()[:120] or 'unnamed', kind, version,
                                                           _pack(proposals_text) if proposals_text is not None else None,
                                                           log_id, json.dumps(gone))).lastrowid
    return {'id': cid, 'name': name, 'kind': kind}


def checkpoints() -> list[dict]:
    """Every saved state, newest first, with how many changes came after it"""
    with connect() as con:
        rows = con.execute('SELECT c.id, c.at, c.name, c.kind, v.size, c.log_id FROM checkpoints c '
                           'JOIN versions v ON v.id = c.version ORDER BY c.id DESC').fetchall()
        out = []
        for cid, at, name, kind, size, log_id in rows:
            since = con.execute('SELECT COUNT(*) FROM curation WHERE id > ? AND reverted = 0', (log_id,)).fetchone()[0]
            out.append({'id': cid, 'at': at, 'name': name, 'kind': kind, 'size': size, 'changes_since': since})
        return out


def restore(cid: int) -> tuple[dict, str, str | None]:
    """A checkpoint and its saved motif index and proposals texts"""
    with connect() as con:
        row = con.execute('SELECT c.id, c.at, c.name, v.data, c.proposals, c.log_id, c.reverted_ids FROM checkpoints c '
                          'JOIN versions v ON v.id = c.version WHERE c.id = ?', (cid,)).fetchone()
    if not row:
        raise ValueError(f'no such checkpoint: {cid}')
    return ({'id': row[0], 'at': row[1], 'name': row[2], 'log_id': row[5], 'reverted_ids': json.loads(row[6])},
            _unpack(row[3]), _unpack(row[4]) if row[4] else None)


def set_reverted(cp: dict) -> int:
    """The log as checkpoint `cp` knew it: what came after it taken back, and of what came before, just what had been
    taken back then (going back to a 'before going back' checkpoint gives back the changes the first going back took
    back). How many changes are now taken back that weren't"""
    with connect() as con:
        was = {r[0] for r in con.execute('SELECT id FROM curation WHERE reverted = 1')}
        gone = set(cp['reverted_ids']) | {r[0] for r in con.execute('SELECT id FROM curation WHERE id > ?', (cp['log_id'],))}
        con.execute('UPDATE curation SET reverted = 0')
        con.executemany('UPDATE curation SET reverted = 1 WHERE id = ?', [(i,) for i in gone])
    return len(gone - was)


def thin(keep_all: td = KEEP_ALL) -> int:
    """Versions older than `keep_all` thinned to the last of each hour; a checkpoint's version always stays"""
    cutoff = (dt.now() - keep_all).isoformat(timespec='seconds')
    with connect() as con:
        keep = {r[0] for r in con.execute('SELECT version FROM checkpoints')}
        keep |= {r[0] for r in con.execute('SELECT MAX(id) FROM versions WHERE at < ? GROUP BY substr(at, 1, 13)', (cutoff,))}
        old = [r[0] for r in con.execute('SELECT id FROM versions WHERE at < ?', (cutoff,)) if r[0] not in keep]
        con.executemany('DELETE FROM versions WHERE id = ?', [(i,) for i in old])
    return len(old)
