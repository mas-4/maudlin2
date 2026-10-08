"""app/health.py: a regular feed gone quiet, one that never builds up, and an outlet missing from its front page are
flagged; a feed quiet for its usual stretch isn't."""
import sqlite3
from datetime import datetime as dt, timedelta as td

from app import health


def db():
    con = sqlite3.connect(':memory:')
    con.execute('CREATE TABLE side_item (source, published, first_seen)')
    con.execute('CREATE TABLE agency (id, name)')
    con.execute('CREATE TABLE article (agency_id, last_accessed)')
    return con


def test_quiet_and_stunted_feeds_and_missing_outlets_are_flagged():
    now = dt(2026, 10, 8, 12)
    con = db()
    day = lambda n: str(now - td(days=n))  # noqa: E731
    con.executemany('INSERT INTO side_item VALUES (?, ?, ?)',
                    [('daily', day(6 + i), day(6 + i)) for i in range(10)]  # daily, silent for 6 days
                    + [('weekly', day(7 * i + 2), day(7 * i + 2)) for i in range(10)]  # weekly, 2 days since: fine
                    + [('stuck', day(5), day(5))])  # one item in five days
    sources = [{'key': k, 'name': k} for k in ('daily', 'weekly', 'stuck', 'never')]
    got = {p['feed']: p['problem'] for p in health.quiet_feeds(con, now, sources)}
    assert set(got) == {'daily', 'stuck', 'never'}
    assert got['daily'].startswith('nothing new in 6 days') and got['stuck'] == 'only 1 saved in all'
    con.executemany('INSERT INTO agency VALUES (?, ?)', [(1, 'Up'), (2, 'Down')])
    con.executemany('INSERT INTO article VALUES (?, ?)', [(1, str(now - td(hours=1))), (2, str(now - td(hours=9)))])
    assert [p['outlet'] for p in health.missing_outlets(con, now)] == ['Down']
