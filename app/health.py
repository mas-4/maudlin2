"""Is the news still coming in? (Oct 8: five podcasts had silently stopped saving episodes four days before anyone
noticed, and six video feeds had followed channels that went quiet.) After each run's reading: every outlet should
have been seen on its front page in the last OUTLET_HOURS, and every side feed that posts regularly should have
something new within QUIET_TIMES its usual gap between posts (at least QUIET_DAYS days). What's wrong is logged as a
warning and kept in HEALTH for the checker and whoever looks."""
import os
import sqlite3
import statistics
from datetime import UTC, datetime as dt, timedelta as td

from app.utils import Config, get_logger
from app.utils.store import write_json

logger = get_logger(__name__)

HEALTH = os.path.join(Config.data, 'health.json')
OUTLET_HOURS = 6
QUIET_DAYS = 3
QUIET_TIMES = 4
REGULAR_DAYS = 14  # a feed whose usual gap is longer than this (a monthly newsletter) isn't watched
HISTORY = 20  # posts a feed's usual gap is read from


def _db():
    return sqlite3.connect(f'file:{Config.connection_string.removeprefix("sqlite:///")}?mode=ro', uri=True)


def quiet_feeds(con, now: dt, sources: list[dict]) -> list[dict]:
    """Side feeds that post regularly but have had nothing new for far longer than usual"""
    out = []
    for s in sources:
        rows = con.execute('SELECT coalesce(published, first_seen), first_seen FROM side_item WHERE source = ? '
                           'ORDER BY coalesce(published, first_seen) DESC LIMIT ?', (s['key'], HISTORY)).fetchall()
        times = sorted(dt.fromisoformat(str(r[0])[:19]) for r in rows if r[0])
        if len(times) < 4:  # too little to read a usual gap from: a feed that never builds up is wrong too
            if not rows:
                out.append({'feed': s['name'], 'problem': 'nothing ever saved'})
            elif now - min(dt.fromisoformat(str(r[1])[:19]) for r in rows) > td(days=QUIET_DAYS):
                out.append({'feed': s['name'], 'problem': f'only {len(rows)} saved in all'})
            continue
        gap = statistics.median((b - a).total_seconds() / 86400 for a, b in zip(times, times[1:]))
        if gap > REGULAR_DAYS:
            continue
        newest = max(dt.fromisoformat(str(r[1])[:19]) for r in rows)
        quiet = (now - newest).total_seconds() / 86400
        if quiet > max(QUIET_DAYS, QUIET_TIMES * gap):
            out.append({'feed': s['name'], 'problem': f'nothing new in {quiet:.0f} days (usually every {gap:.1f})'})
    return out


def missing_outlets(con, now: dt) -> list[dict]:
    """Outlets not seen on their front page lately (a scraper broken by a redesign, or a site down)"""
    since = (now - td(hours=OUTLET_HOURS)).isoformat(sep=' ')
    rows = con.execute('SELECT a.name, max(ar.last_accessed) FROM agency a LEFT JOIN article ar ON ar.agency_id = a.id '
                       'GROUP BY a.id').fetchall()
    return [{'outlet': name, 'problem': f'not seen since {(last or "never")[:16]}'} for name, last in rows
            if not last or last < since]


def check() -> list[dict]:
    from app import sidefeeds
    now = dt.now(UTC).replace(tzinfo=None)
    con = _db()
    try:
        problems = missing_outlets(con, now) + quiet_feeds(con, now, sidefeeds.SOURCES)
    finally:
        con.close()
    for p in problems:
        logger.warning("Health: %s: %s", p.get('outlet') or p.get('feed'), p['problem'])
    write_json(HEALTH, {'at': now.isoformat(timespec='seconds'), 'problems': problems})
    if not problems:
        logger.info("Health: every outlet and regular feed is coming in")
    return problems
