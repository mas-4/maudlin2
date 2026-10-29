"""Historical echoes (Oct 28): today's motifs told in 1896 newspapers, each one approved by the person
(scripts/echoes.py proposes them and records the person's verdicts; the site's echoes page shows the approved ones).

The 1896 claims are Rip Van Winkle's (papers/rip-van-winkle.md): 520 political articles of 1896 from American Stories
(Chronicling America's page scans read by OCR), their claims filed to a copy of today's motif index. Kept in
archives/archives.sqlite, table echoes."""
import functools
import os
import re
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


RUN_WORDS = 6  # a passage: six words in a row (of three letters or more, so OCR's stray marks don't count)
SAME_TEXT = 0.15  # an article is a reprint of another when this share of the shorter one's six-word runs are in both
SAME_TEXT_RUNS = 20  # and at least this many: a passage, not a stock phrase


def runs(text: str) -> set[str]:
    words = re.findall(r'[a-z]{3,}', (text or '').lower())
    return {' '.join(words[i:i + RUN_WORDS]) for i in range(len(words) - RUN_WORDS + 1)}


def reprinted(articles: dict[str, tuple[str, str]]) -> dict[str, int]:
    """Article id -> how many papers printed it, counting its own (Oct 29). articles: id -> (paper, text). A paper
    counts when one of its articles shares a passage word for word with this one, as 1896's exchange papers reprinted
    each other. Until Oct 29 the count was of papers with a claim like it, joined in chains (app.narratives.groups),
    which ran through a whole topic: eleven different silver and gold claims each showed "60 papers"."""
    shingles = {k: runs(t) for k, (_, t) in articles.items()}
    papers = {k: {p} for k, (p, _) in articles.items()}
    keys = [k for k in articles if shingles[k]]
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            shared = len(shingles[a] & shingles[b])
            if shared >= SAME_TEXT_RUNS and shared >= SAME_TEXT * min(len(shingles[a]), len(shingles[b])):
                papers[a].add(articles[b][0])
                papers[b].add(articles[a][0])
    return {k: len(v) for k, v in papers.items()}


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
