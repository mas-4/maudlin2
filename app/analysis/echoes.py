"""Historical echoes (Oct 28): today's motifs told in 1896 newspapers, each one approved by the person
(scripts/echoes.py proposes them and records the person's verdicts; the site's echoes page shows the approved ones).

The 1896 claims are Rip Van Winkle's (papers/rip-van-winkle.md): 520 political articles of 1896 from American Stories
(Chronicling America's page scans read by OCR), their claims filed to a copy of today's motif index. Kept in
archives/archives.sqlite, table echoes."""
import functools
import os
import sqlite3

from app.utils import Config

DB = os.path.join(Config.data, 'archives', 'archives.sqlite')
SCHEMA = """create table if not exists echoes (
    id integer primary key, motif text not null, motif_name text not null, claim integer not null, run text not null,
    claim_text text, quote text, quote_clean text, headline text, paper text, place text, date text, url text,
    fit real, retold integer, status text not null default 'proposed', why text, proposed_at text, decided_at text,
    reviewer text, unique (motif, claim))"""
REVIEWERS = ('person', 'claude')  # who checked an echo: the person, or Claude (Opus 5.5) reading the whole article
STATUSES = ('proposed', 'approved', 'rejected', 'held')  # held: for the person (near a slur or trope, or a close call)


def connect(write: bool = False, path: str | None = None) -> sqlite3.Connection:
    path = path or DB
    con = sqlite3.connect(path if write else f'file:{path}?mode=ro', uri=not write, timeout=120)
    con.row_factory = sqlite3.Row
    if write:
        con.execute(SCHEMA)
        if 'reviewer' not in {r[1] for r in con.execute('pragma table_info(echoes)')}:  # tables made before Oct 28 evening
            con.execute('alter table echoes add column reviewer text')
            con.execute("update echoes set reviewer = 'person' where status != 'proposed'")
            con.commit()
    return con


def approved(path: str | None = None) -> list[dict]:
    """The echoes the person approved, the most reprinted first; empty when there's no table yet"""
    try:
        con = connect(path=path)
        try:
            rows = con.execute("select * from echoes where status = 'approved' "
                               "order by retold desc, fit desc, id").fetchall()
        finally:
            con.close()
        return [dict(r) for r in rows]
    except sqlite3.Error:
        return []


@functools.lru_cache(maxsize=1)
def any_approved() -> bool:
    """Whether the echoes page has anything to show (the menu leaves it out until it has), once a build"""
    return bool(approved())
