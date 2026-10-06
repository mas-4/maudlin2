"""TV news chyrons (the captions along the bottom of the screen) from the Internet Archive's TV News Archive "Third
Eye" service: the words on screen on BBC News, CNN, Fox News and MSNOW (MSNBC), read by OCR about once a minute, with
how many seconds each stayed up. Beside the hourly front pages they show what television kept in front of viewers, and
for how long.

Polite by design: one request a run for the current UTC day (the service fills in through the day), and one more to
finish the day before once it's over. Each day is kept whole as the service sends it, in data/chyrons/YYYY-MM-DD.tsv
(times in UTC), so the raw record stays as it was read; cleaning the OCR and matching to stories work from these files.
https://archive.org/services/third-eye.php"""
import csv
import os
import re
from datetime import datetime as dt, timedelta as td

import requests as rq

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

URL = 'https://archive.org/services/third-eye.php'
FOLDER = os.path.join(Config.data, 'chyrons')
STATE = os.path.join(FOLDER, 'state.json')  # days fetched after they were over: never asked for again
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
CHANNELS = {'BBCNEWS': 'BBC News', 'CNNW': 'CNN', 'FOXNEWSW': 'Fox News', 'MSNOW': 'MSNOW'}


def path(day: str) -> str:
    return os.path.join(FOLDER, f'{day}.tsv')


def fetch_day(day: str) -> int | None:
    """Fetch one UTC day (YYYY-MM-DD) and keep it as sent; the number of rows, or None on an error"""
    y, m, d = day.split('-')
    try:
        r = rq.get(URL, params={'dayL': f'{m}/{d}/{y}', 'dayR': f'{m}/{d}/{y}'}, timeout=120,
                   headers={'User-Agent': USER_AGENT})
        r.raise_for_status()
    except rq.RequestException as e:
        logger.warning("Chyrons: %s not fetched (%s)", day, e)
        return None
    text = r.text
    if not text.startswith('date_time'):
        logger.warning("Chyrons: %s came back in an unexpected shape", day)
        return None
    os.makedirs(FOLDER, exist_ok=True)
    with open(path(day) + '.tmp', 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(path(day) + '.tmp', path(day))
    return text.count('\n') - 1


def fetch_chyrons(now: dt | None = None):
    """Each run: today's chyrons so far (UTC), and yesterday's once more after it's over, then never again"""
    now = now or dt.utcnow()
    state = read_json(STATE, {'done': []})
    today, yesterday = now.strftime('%Y-%m-%d'), (now - td(days=1)).strftime('%Y-%m-%d')
    if yesterday not in state['done']:
        rows = fetch_day(yesterday)
        if rows is not None:
            state['done'] = sorted(set(state['done']) | {yesterday})
            write_json(STATE, state)
    rows = fetch_day(today)
    if rows is not None:
        logger.info("Chyrons: %d rows so far today (UTC)", rows)


def rows(day: str) -> list[dict]:
    """A day's chyrons: time (UTC), channel, seconds on screen, the program (from the Archive's id) and the OCR text"""
    try:
        with open(path(day), encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            next(reader, None)
            out = []
            for r in reader:
                if len(r) < 5 or r[1] not in CHANNELS:
                    continue
                program = re.sub(r'^[A-Z]+_\d{8}_\d{6}_', '', r[3].split('/')[0]).replace('_', ' ').strip()
                out.append({'at': dt.strptime(r[0], '%Y-%m-%d %H:%M:%S'), 'channel': r[1], 'seconds': int(r[2] or 0),
                            'program': program, 'link': 'https://archive.org/details/' + r[3],
                            'text': r[4].replace('\\n', '\n').strip()})
            return out
    except OSError:
        return []
