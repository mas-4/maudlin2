"""Which scrapers look broken: after each run, a short list to check (data/scraper_check.md), with the reason for each.

Every scraper's numbers are recorded as it finishes (headlines found, kept, dropped as too long, and whether its page
loaded at all) and kept for the last HISTORY runs (data/scraper_history.json). A scraper makes the list when, this
run, it failed to load its page, found nothing, kept nothing of what it found, found far fewer than it usually does,
dropped most of what it found as too long (its parser grabbing summaries), or hasn't added a new headline in two
days.
A healthy run writes a list that says so."""
import os
import threading
from datetime import datetime as dt
from statistics import median

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

HISTORY_FILE = os.path.join(Config.data, 'scraper_history.json')
CHECK_FILE = os.path.join(Config.data, 'scraper_check.md')
HISTORY = 72  # runs kept per scraper (three days of hourly runs)
DROP = 0.4  # found under this share of its usual number
MIN_RUNS = 5  # runs of history before "usual" means anything
STALE_RUNS = 48  # runs in a row adding nothing new: stale (two days, so a weekday outlet's quiet weekend isn't)
TOO_LONG = 0.5  # dropping this share of what it found as too long

_runs: dict[str, dict] = {}
_lock = threading.Lock()


def record(agency: str, url: str, found: int = 0, kept: int = 0, added: int = 0, too_long: int = 0,
           error: str | None = None):
    """One scraper's numbers for this run (thread-safe; the scrapers finish on several threads)."""
    with _lock:
        _runs[agency] = {'at': dt.now().isoformat(timespec='minutes'), 'url': url, 'found': found, 'kept': kept,
                         'added': added, 'too_long': too_long, 'error': error}


def problems(agency: str, now: dict, past: list[dict]) -> list[str]:
    """Why this scraper needs a look, from this run and its earlier ones."""
    if now.get('error'):
        failed = 1 + sum(1 for r in past[-2:] if r.get('error'))
        return [f"page didn't load ({now['error']})" + (f', {failed} runs in a row' if failed > 1 else '')]
    out = []
    usual = median([r['found'] for r in past if not r.get('error')]) if len(past) >= MIN_RUNS else None
    if now['found'] == 0:
        out.append('found no headlines' + (f' (usually {usual:g})' if usual else ''))
    elif now['kept'] == 0:
        out.append(f"found {now['found']} but kept none: the parser may be picking the wrong elements")
    elif usual and now['found'] < DROP * usual:
        out.append(f"found {now['found']}, usually {usual:g}")
    if now['found'] and now['too_long'] >= TOO_LONG * now['found']:
        out.append(f"dropped {now['too_long']} of {now['found']} as too long: the parser may be grabbing summaries")
    recent = (past + [now])[-STALE_RUNS:]
    if len(recent) >= STALE_RUNS and not any(r.get('added') for r in recent) and now['found']:
        out.append(f'no new headline in {STALE_RUNS} runs: the page may be stuck or cached')
    return out


def write(expected: list[tuple[str, str]] | None = None) -> list[tuple[str, list[str]]]:
    """Add this run to the history and write the list to check. `expected`: (agency, url) of every scraper meant to
    run, so one that never reported (crashed before finishing) is listed too."""
    with _lock:
        runs = dict(_runs)
        _runs.clear()
    for agency, url in expected or []:
        runs.setdefault(agency, {'at': dt.now().isoformat(timespec='minutes'), 'url': url, 'found': 0, 'kept': 0,
                                 'added': 0, 'too_long': 0, 'error': 'never finished'})
    history = read_json(HISTORY_FILE, {})
    flagged = []
    for agency, now in sorted(runs.items()):
        past = history.get(agency, [])
        found = problems(agency, now, past)
        if found:
            flagged.append((agency, found))
        history[agency] = (past + [now])[-HISTORY:]
    write_json(HISTORY_FILE, history)
    stamp = dt.now().strftime('%Y-%m-%d %H:%M')
    lines = [f'# Scrapers to check ({stamp})', '']
    if flagged:
        lines += [f"- **{agency}** ({runs[agency]['url']}): " + '; '.join(why) for agency, why in flagged]
    else:
        lines.append(f'All {len(runs)} scrapers look healthy.')
    with open(CHECK_FILE, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    logger.info("Scraper check: %d of %d to look at (%s)", len(flagged), len(runs), CHECK_FILE)
    return flagged
