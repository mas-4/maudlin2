"""The archive experiments' own database (Oct 11, the person: "you're building databases with this analysis right so we
can revisit and experiment?"). One SQLite file beside the archives, never the site's database: every document an A
experiment reads (an 1896 article, a folktale, a speech), the claims a model read from it, where each claim was filed
in which run and with what fit, the motifs as they stood for that run (the live index moves on), and verdicts, the
person's spot-checks and outside labels (a tale's ATU type).

    documents  (corpus, id) -> title, date, place, source, url (the page scan), text, meta (JSON); searchable by
               word through documents_fts (search())
    claims     id -> corpus, document, text, model, prompt (a hash of the prompt's wording), run
    runs       id -> experiment, stage, at, commit, notes
    motifs     (run, id) -> name, note, genre, new (made in that run)
    filings    (run, claim, motif) -> fit, sure
    verdicts   (claim, motif, by) -> answer (yes/no or a label), at

Read it with sqlite3 or pandas; the experiments write it through the functions here."""
import hashlib
import json
import os
import sqlite3
import subprocess
from datetime import datetime as dt

from app.utils import Config

DB = os.path.join(Config.data, 'archives', 'archives.sqlite')
SCHEMA = """
create table if not exists documents (corpus text, id text, title text, date text, place text, source text, url text,
    text text, meta text, primary key (corpus, id));
create table if not exists runs (id text primary key, experiment text, stage text, at text, git_commit text, notes text);
create table if not exists claims (id integer primary key, corpus text, document text, text text, model text,
    prompt text, run text, unique (corpus, document, text, prompt));
create table if not exists motifs (run text, id text, name text, note text, genre text, new integer,
    primary key (run, id));
create table if not exists filings (run text, claim integer, motif text, fit real, sure integer,
    primary key (run, claim, motif));
create table if not exists verdicts (claim integer, motif text, by text, answer text, at text,
    primary key (claim, motif, by));
create index if not exists claims_document on claims (corpus, document);
create index if not exists filings_motif on filings (motif);
"""


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB), exist_ok=True)
    con = sqlite3.connect(DB, timeout=60)
    con.executescript(SCHEMA)
    return con


def prompt_id(prompt: str) -> str:
    return hashlib.sha1(prompt.encode()).hexdigest()[:10]


def run(experiment: str, stage: str, notes: str = '') -> str:
    """A run's id, recorded with the code it ran on"""
    commit = subprocess.run(['git', '-C', os.path.dirname(os.path.abspath(__file__)), 'rev-parse', '--short', 'HEAD'],
                            capture_output=True, text=True).stdout.strip()
    at = dt.now().isoformat(timespec='seconds')
    rid = f'{experiment}:{stage}:{at}'
    with connect() as con:
        con.execute('insert into runs values (?, ?, ?, ?, ?, ?)', (rid, experiment, stage, at, commit, notes))
    return rid


def documents(corpus: str, docs: list[dict]):
    """docs: {'id', 'title', 'date', 'place', 'source', 'url', 'text', and anything else (into meta)}"""
    base = {'id', 'title', 'date', 'place', 'source', 'url', 'text'}
    with connect() as con:
        # an upsert, not 'insert or replace': that gives the row a new rowid and leaves the word index pointing at the old
        con.executemany('insert into documents values (?, ?, ?, ?, ?, ?, ?, ?, ?) on conflict (corpus, id) do update set '
                        'title = excluded.title, date = excluded.date, place = excluded.place, source = excluded.source, '
                        'url = excluded.url, text = excluded.text, meta = excluded.meta',
                        [(corpus, d['id'], d.get('title'), d.get('date'), d.get('place'), d.get('source'), d.get('url'),
                          d.get('text'), json.dumps({k: v for k, v in d.items() if k not in base})) for d in docs])


def claims(corpus: str, document: str, texts: list[str], model: str, prompt: str, run_id: str) -> list[int]:
    """The claims' ids (a claim already read from that document with that prompt keeps its id)"""
    pid = prompt_id(prompt)
    out = []
    with connect() as con:
        for t in texts:
            con.execute('insert or ignore into claims (corpus, document, text, model, prompt, run) values (?, ?, ?, ?, ?, ?)',
                        (corpus, document, t, model, pid, run_id))
            out.append(con.execute('select id from claims where corpus = ? and document = ? and text = ? and prompt = ?',
                                   (corpus, document, t, pid)).fetchone()[0])
    return out


def claim_id(corpus: str, text: str) -> int | None:
    with connect() as con:
        row = con.execute('select id from claims where corpus = ? and text = ? order by id limit 1', (corpus, text)).fetchone()
    return row[0] if row else None


def motifs(run_id: str, entries: list[dict], new: set[str] = frozenset()):
    """The motifs as they stood for a run: name, note, genre"""
    with connect() as con:
        con.executemany('insert or replace into motifs values (?, ?, ?, ?, ?, ?)',
                        [(run_id, e['id'], e.get('name'), e.get('note'), (e.get('facets') or {}).get('genre'),
                          int(e['id'] in new)) for e in entries])


def filings(run_id: str, rows: list[tuple[int, str, float | None, bool]]):
    """rows: (claim id, motif id, fit, sure)"""
    with connect() as con:
        con.executemany('insert or replace into filings values (?, ?, ?, ?, ?)',
                        [(run_id, c, m, f, int(bool(s))) for c, m, f, s in rows])


def index_text():
    """The full-text index over every document's title and text, built again (after a big load)"""
    with connect() as con:
        con.execute("create virtual table if not exists documents_fts using fts5(title, text, content='documents', "
                    "content_rowid='rowid')")
        con.execute("insert into documents_fts(documents_fts) values ('rebuild')")


def search(query: str, corpus: str | None = None, limit: int = 50) -> list[dict]:
    """Documents matching an FTS5 query ('"crime of 73"', 'rothschild AND gold'), best first"""
    con = connect()
    con.row_factory = sqlite3.Row
    rows = con.execute("select d.corpus, d.id, d.title, d.date, d.source, d.url, snippet(documents_fts, 1, '[', ']', '…', 20) "
                       'as snippet from documents_fts join documents d on d.rowid = documents_fts.rowid '
                       'where documents_fts match ? and (? is null or d.corpus = ?) order by rank limit ?',
                       (query, corpus, corpus, limit)).fetchall()
    return [dict(r) for r in rows]


def verdict(claim: int, motif: str, by: str, answer: str):
    with connect() as con:
        con.execute('insert or replace into verdicts values (?, ?, ?, ?, ?)',
                    (claim, motif, by, answer, dt.now().isoformat(timespec='seconds')))
