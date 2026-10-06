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


# Cleaning: the OCR misreads letters (O for 0, 1 IVE for LIVE, NICOI I E for NICOLLE) and catches more than headlines
# (the network's logo, the clock, guests' names, ads). A small local model reads each day's distinct lines in batches,
# with the channel, the program and the day's story headlines for names, says what each line is and corrects the
# headlines. Kept in data/chyrons/clean.json (channel + OCR line -> kind and text): the raw files never change.
CLEAN = os.path.join(FOLDER, 'clean.json')
# Gemma 4 12B: on a test batch (Oct 6) it sorted the lines well and invented nothing; Gemma 4 26B "corrected" a steel
# plant in Iowa to one in Ohio, and Qwen3 8B kept garbled promos as headlines
CLEAN_MODEL = 'gemma4:12b'
BATCH = 30
KINDS = ['headline', 'name', 'promo', 'ad', 'junk']
CLEAN_PROMPT = """Lines read by OCR from the captions at the bottom of the screen on {channel} ({programs}). OCR misreads \
letters: O for 0, I for L, 1 for I, run-together or broken words, stray marks.

Today's news, for names and terms the captions may mention:
{news}

{lines}

For each line, by its number:
kind: "headline" for a news caption (what is happening), "name" for a person's name and title, "promo" for the \
program's or network's own caption (what's next, the show's title, a logo), "ad" for an advertisement, "junk" for \
the clock, stray letters or anything unreadable
text: for a headline or name, the line as it was meant to read, corrected for OCR errors only, in its own \
capitalization: don't add, explain, guess or rewrite; for anything else, empty"""


# BBC's logo, alone or after a headline's full stop ('... election. BB E NEWS'); not 'BIG NEWS' ending a headline
LOGO = re.compile(r'(?:^|\.)\s*B[A-Z€ ]{0,5}N\s?E\s?W\s?S(\s+BUSINESS TODAY)?\W*$', re.I)


def caption_lines(text: str):
    """A row's caption lines: split at line breaks and where OCR ran a headline and a name caption together ('. .'),
    BBC's logo cut off the end ('Quebec separatist party projected to win election. BB E NEWS'), tidied"""
    for raw in text.split('\n'):
        for part in re.split(r'\.\s+\.\s+', raw):
            line = ' '.join(LOGO.sub('', part.strip()).split()).strip(' .|')
            if line:
                yield line


def line_key(channel: str, line: str) -> str:
    return channel + '|' + ' '.join(line.split())


def lines_of(day: str) -> dict[str, dict]:
    """The day's distinct caption lines per channel, with the programs they appeared in and their seconds on screen"""
    out = {}
    for r in rows(day):
        for line in caption_lines(r['text']):
            if len(line) < 4:
                continue
            e = out.setdefault(line_key(r['channel'], line), {'channel': r['channel'], 'line': line, 'programs': set(),
                                                              'seconds': 0})
            e['programs'].add(r['program'])
            e['seconds'] += r['seconds']
    return out


JUNK = re.compile(r'^\W*[1lIT]\s?[IL1]?IVE\b|^\W*LIVE\s*[>S]', re.I)  # MSNOW's clock ("1 IVE > 9:47am"); logos are cut
# off by LOGO, and what's left of a logo-only line is too short to keep
SAME = 0.8  # lines this alike (letters and digits) on one channel are one caption read slightly differently


def save_clean(found: dict):
    """Add cleaned lines to CLEAN, merged with what's there under a lock: the hourly run and a backfill may clean at
    once, and each saving its own whole copy lost the other's work"""
    from app.utils.store import locked
    with locked(CLEAN):
        store = read_json(CLEAN, {})
        store.update(found)
        write_json(CLEAN, store)


def groups(lines: list[dict]) -> list[list[dict]]:
    """Near-identical lines of one channel together, the longest on screen first in each: the same caption read by
    OCR a little differently minute to minute is cleaned once"""
    import difflib
    out = []
    for e in sorted(lines, key=lambda e: -e['seconds']):
        norm = re.sub(r'[^a-z0-9 ]', '', e['line'].lower())
        for g in out:
            sm = difflib.SequenceMatcher(None, norm, g['norm'])
            if sm.real_quick_ratio() >= SAME and sm.quick_ratio() >= SAME and sm.ratio() >= SAME:
                g['members'].append(e)
                break
        else:
            out.append({'norm': norm, 'members': [e]})
    return [g['members'] for g in out]


def clean_day(day: str, news: list[str], budget: float | None = None) -> int:
    """Clean the day's lines not cleaned yet, for at most `budget` seconds; how many were cleaned. Lines too short to
    be a caption, the clock and logos are junk without asking; the rest are grouped (near-identical lines of a
    channel) and one line of each group goes to the model, its answer kept for the whole group."""
    import time
    from app.analysis import llm
    store = read_json(CLEAN, {})
    todo = [e for k, e in lines_of(day).items() if k not in store]
    found = {}
    if not todo or llm.backend() is None:
        return 0
    done = 0
    for e in todo:
        if sum(c.isalpha() for c in e['line']) < 12 or JUNK.search(e['line']):
            store[line_key(e['channel'], e['line'])] = found[line_key(e['channel'], e['line'])] = {'kind': 'junk', 'text': ''}
            done += 1
    started = time.time()
    for channel in CHANNELS:
        mine = groups([e for e in todo if e['channel'] == channel and line_key(channel, e['line']) not in store])
        for i in range(0, len(mine), BATCH):
            if budget is not None and time.time() - started > budget:
                save_clean(found)
                return done
            batch = mine[i:i + BATCH]
            programs = sorted({p for g in batch for e in g for p in e['programs']})[:4]
            schema = {"type": "object", "properties": {"lines": {"type": "array", "items": {"type": "object", "properties": {
                "n": {"type": "integer", "minimum": 1, "maximum": len(batch)}, "kind": {"type": "string", "enum": KINDS},
                "text": {"type": "string", "maxLength": 200}}, "required": ["n", "kind", "text"]}}}, "required": ["lines"]}
            answer = llm.complete_json(CLEAN_PROMPT.format(
                channel=CHANNELS[channel], programs='; '.join(programs), news='\n'.join(f'- {h}' for h in news[:40]),
                lines='\n'.join(f'{n}. {g[0]["line"]}' for n, g in enumerate(batch, 1))), schema, max_tokens=4000,
                model=CLEAN_MODEL)
            for x in (answer or {}).get('lines', []):
                n = x.get('n')
                if isinstance(n, int) and 1 <= n <= len(batch) and x.get('kind') in KINDS:
                    for e in batch[n - 1]:
                        store[line_key(channel, e['line'])] = found[line_key(channel, e['line'])] = {
                            'kind': x['kind'], 'text': ' '.join(x.get('text', '').split())}
                        done += 1
            save_clean(found)
    save_clean(found)
    return done


def day_news(day: str) -> list[str]:
    """The labels of the stories on the front pages that day (UTC), most outlets first: names and terms for cleaning"""
    from app.models import Session, Story, StorySnapshot
    from sqlalchemy import func
    start = dt.strptime(day, '%Y-%m-%d')
    with Session() as s:
        rows = s.query(Story.label, func.max(StorySnapshot.outlets)).join(StorySnapshot, StorySnapshot.story_id == Story.id) \
            .filter(StorySnapshot.at >= start, StorySnapshot.at < start + td(days=1)).group_by(Story.id).all()
    return [label for label, n in sorted(rows, key=lambda r: -(r[1] or 0)) if label]


def clean_recent(budget: float = 180, now: dt | None = None) -> int:
    """Clean yesterday's leftover lines, then today's, for at most `budget` seconds in all"""
    import time
    now, started, done = now or dt.utcnow(), time.time(), 0
    for day in ((now - td(days=1)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')):
        left = budget - (time.time() - started)
        if left <= 0 or not os.path.exists(path(day)):
            continue
        done += clean_day(day, day_news(day), budget=left)
    if done:
        logger.info("Chyrons: %d caption lines cleaned", done)
    return done


# Matching: each headline caption to the story on the front pages it's about, by meaning against the stories'
# headlines at the nearest run (an hour's front pages), when it's at least MATCH alike
MATCH = 0.75  # mxbai cosine; checked by hand on Oct 5's captions
NEAR = td(minutes=50)


def front_at(when: dt) -> list[dict]:
    """The stories at the run nearest a time (within NEAR), each with its label, outlets then and headlines"""
    from app.models import Session, Story, StorySnapshot, StoryHeadline, Headline
    with Session() as s:
        runs = [r for (r,) in s.query(StorySnapshot.at).filter(StorySnapshot.at.between(when - NEAR, when + NEAR)).distinct()]
        if not runs:
            return []
        run = min(runs, key=lambda r: abs(r - when))
        stories = {i: {'id': i, 'label': label or '', 'outlets': n, 'headlines': []} for i, label, n in s.query(
            Story.id, Story.label, StorySnapshot.outlets).join(StorySnapshot, StorySnapshot.story_id == Story.id)
            .filter(StorySnapshot.at == run)}
        for sid, title in s.query(StoryHeadline.story_id, Headline.title).join(Headline, Headline.id == StoryHeadline.headline_id) \
                .filter(StoryHeadline.story_id.in_(list(stories))):
            if title and len(stories[sid]['headlines']) < 12:
                stories[sid]['headlines'].append(title)
    ranked = sorted(stories.values(), key=lambda st: -st['outlets'])
    for n, st in enumerate(ranked, 1):
        st['rank'] = n
    return ranked


def headlines_of(day: str) -> list[dict]:
    """The day's headline captions as cleaned: one per row and caption, with its time, channel, seconds and text"""
    store = read_json(CLEAN, {})
    out = []
    for r in rows(day):
        for line in caption_lines(r['text']):
            c = store.get(line_key(r['channel'], line))
            if c and c['kind'] == 'headline' and c['text']:
                out.append({'at': r['at'], 'channel': r['channel'], 'seconds': r['seconds'], 'program': r['program'],
                            'text': c['text']})
    return out


MATCHES = os.path.join(FOLDER, 'matches.json')  # channel|hour|caption -> story id (0: none), as the model answered
MATCH_MODEL = 'gemma4:26b'
MATCH_FRONT = 80  # the front pages' stories offered to the model (an hour has about 65; at 40 a stabbing story ranked 47th was missed)
MATCH_BATCH = 40  # captions a call
MATCH_PROMPT = """Captions (chyrons) {channel} showed at the bottom of the screen during one hour, numbered:
{captions}

The stories on the news sites' front pages that hour, lettered:
{front}

For each caption, by its number: the letter of the front-page story it is about (the same news event, not just the \
same topic or person), or "none"."""


def letters(n: int) -> list[str]:
    import string
    a = string.ascii_uppercase
    return [a[i] if i < 26 else a[i // 26 - 1] + a[i % 26] for i in range(n)]


def judge_hour(channel: str, texts: list[str], front: list[dict]) -> dict[str, int] | None:
    """caption -> story id (0: none) for one channel-hour, by the model; None if it couldn't answer"""
    from app.analysis import llm
    tags = letters(len(front))
    out = {}
    for i in range(0, len(texts), MATCH_BATCH):
        batch = texts[i:i + MATCH_BATCH]
        schema = {"type": "object", "properties": {"captions": {"type": "array", "items": {"type": "object", "properties": {
            "n": {"type": "integer", "minimum": 1, "maximum": len(batch)},
            "story": {"type": "string", "enum": tags + ['none']}}, "required": ["n", "story"]}}}, "required": ["captions"]}
        answer = llm.complete_json(MATCH_PROMPT.format(
            channel=CHANNELS[channel], captions='\n'.join(f'{n}. {t}' for n, t in enumerate(batch, 1)),
            front='\n'.join(f'{tag}. {st["label"]}' for tag, st in zip(tags, front))), schema, max_tokens=3000, model=MATCH_MODEL)
        if answer is None:
            return None
        for x in answer.get('captions', []):
            n = x.get('n')
            if isinstance(n, int) and 1 <= n <= len(batch):
                out[batch[n - 1]] = front[tags.index(x['story'])]['id'] if x.get('story') in tags else 0
    return out


def match_day(day: str, use_model: bool = True, budget: float | None = None) -> list[dict]:
    """The day's headline captions with the story each is about (or none), hour by hour; kept in
    data/chyrons/matched-<day>.json. The model reads each channel-hour's captions against the front pages' stories at
    the nearest run (embeddings at MATCH missed terse captions such as "U.S. B-1 BOMBERS EVACUATED" and let a few wrong
    ones through, Oct 6); its answers are kept in MATCHES, so a caption is asked about once. Without the model, or
    past `budget` seconds of asking it (the rest is asked next run), embeddings."""
    import time
    import numpy as np
    from app.analysis import llm
    from app.analysis.clustering import ollama_embed
    caps = headlines_of(day)
    by_hour = {}
    for c in caps:
        by_hour.setdefault(c['at'].replace(minute=0, second=0), []).append(c)
    asked = read_json(MATCHES, {})
    model = use_model and llm.backend() is not None
    started = time.time()
    for hour, items in sorted(by_hour.items(), reverse=True):  # the latest hours first: what the page shows
        if model and budget is not None and time.time() - started > budget:
            model = False
        front = front_at(hour + td(minutes=30))
        if not front:
            continue
        byid = {st['id']: st for st in front}
        found = {}
        if model:
            for channel in CHANNELS:
                texts = sorted({c['text'] for c in items if c['channel'] == channel})
                key = lambda t: f"{channel}|{hour.isoformat()}|{t}"  # noqa: E731
                todo = [t for t in texts if key(t) not in asked]
                if todo:
                    got = judge_hour(channel, todo, front[:MATCH_FRONT])
                    if got is None:
                        continue
                    for t, sid in got.items():
                        asked[key(t)] = sid
                    write_json(MATCHES, asked)
                for t in texts:
                    sid = asked.get(key(t))
                    if sid and sid in byid:
                        found[(channel, t)] = {'story': sid, 'label': byid[sid]['label'], 'rank': byid[sid]['rank'],
                                               'outlets': byid[sid]['outlets']}
        if not model:
            texts = sorted({c['text'] for c in items})
            heads = [(st, h) for st in front for h in [st['label']] + st['headlines']]
            v = ollama_embed(texts + [h for _, h in heads])
            sims = v[:len(texts)] @ v[len(texts):].T
            for t, row in zip(texts, sims):
                j = int(np.argmax(row))
                if row[j] >= MATCH:
                    st = heads[j][0]
                    for channel in CHANNELS:
                        found.setdefault((channel, t), {'story': st['id'], 'label': st['label'], 'rank': st['rank'],
                                                        'outlets': st['outlets'], 'score': round(float(row[j]), 3)})
        for c in items:
            c.update(found.get((c['channel'], c['text']), {}))
    out = [{**c, 'at': c['at'].isoformat()} for c in caps]
    write_json(os.path.join(FOLDER, f'matched-{day}.json'), out)
    return out


def match_recent(budget: float = 180, now: dt | None = None):
    """Match today's and yesterday's cleaned headline captions to stories (each run: cleaning fills in through the
    day), the model asked for at most `budget` seconds in all"""
    import time
    now, started = now or dt.utcnow(), time.time()
    for day in (now.strftime('%Y-%m-%d'), (now - td(days=1)).strftime('%Y-%m-%d')):
        if os.path.exists(path(day)):
            try:
                caps = match_day(day, budget=max(0, budget - (time.time() - started)))
                logger.info("Chyrons: %s, %d headline captions, %d matched to a story", day, len(caps),
                            sum(1 for c in caps if c.get('story')))
            except Exception as e:  # noqa: extra; the run goes on without it
                logger.warning("Chyrons: matching %s failed (%s)", day, e)
