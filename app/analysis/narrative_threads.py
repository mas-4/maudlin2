"""Narratives across days: the layers above single posts (#142 follow-up). Posts that tell one thing make a day's group
(a narrative in one day's report, app/narratives.py); the same narrative told again on later days makes a thread,
followed across days like a saga (app/analysis/sagas.py) follows a news story across its parts.

Each day's report (the latest of the day that covers at least six hours) is linked once: each narrative is compared
by meaning with the threads seen in the last WINDOW days, and the closest few are put to the bigger local model, which
says whether it is the same narrative told again or a different one. A narrative with no match starts a thread."""
import glob
import json
import os
from datetime import date, timedelta

import numpy as np

from app.analysis import llm
from app.utils import get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

WINDOW = 14  # days a thread waits to be told again
CANDIDATE = 0.7  # a thread at least this alike (mxbai) is put to the model
CANDIDATES = 3
MIN_HOURS = 6  # reports covering less (early trials) aren't a day
MODEL = 'qwen3:30b-a3b'
PROMPT = """Two claims that many people retold in their own words online, on different days:

Earlier: {a}
Later: {b}

Is the later one the same narrative told again: the same claim about the same people, event or thing, maybe in \
other words or with new details? A different claim about the same person, or the same kind of claim about a \
different event, is a different narrative.

reason: a sentence on why
verdict: "the same narrative" or "different narratives\""""
SCHEMA = {"type": "object", "properties": {"reason": {"type": "string", "maxLength": 600},
                                           "verdict": {"type": "string", "enum": ["the same narrative", "different narratives"]}},
          "required": ["reason", "verdict"]}


def folder() -> str:
    from app import narratives
    return narratives.FOLDER


def store_path() -> str:
    return os.path.join(folder(), 'threads.json')


def load() -> dict:
    return read_json(store_path(), {'next': 1, 'threads': {}, 'linked': [], 'verdicts': {}})


def save(store: dict):
    write_json(store_path(), store, indent=1)


def day_reports() -> list[str]:
    """The report of each day (the latest that covers at least MIN_HOURS), oldest first"""
    by_day = {}
    for path in sorted(glob.glob(os.path.join(folder(), 'report-*.json'))):
        with open(path) as f:
            hours = json.load(f).get('hours', 0)
        if hours >= MIN_HOURS:
            by_day[os.path.basename(path)[7:17]] = path
    return [by_day[d] for d in sorted(by_day)]


def retold(report: dict) -> list[dict]:
    """A report's narratives (the groups the model read as retold), with the facts a thread keeps of each day"""
    out = []
    for g in report['found']:
        label = g.get('label') or {}
        if label.get('retold') and label.get('narrative'):
            out.append({'claim': label['narrative'], 'people': g['authors'], 'posts': g['posts'],
                        'genre': label.get('genre', ''), 'story': (g.get('story') or {}).get('label')})
    return out


def judge(a: str, b: str, store: dict) -> bool:
    key = a + '\n' + b
    if key not in store['verdicts']:
        answer = llm.complete_json(PROMPT.format(a=a, b=b), SCHEMA, max_tokens=500, model=MODEL)
        if not answer or answer.get('verdict') not in SCHEMA['properties']['verdict']['enum']:
            return False  # asked again next time
        store['verdicts'][key] = {'same': answer['verdict'] == 'the same narrative', 'reason': answer.get('reason', '')}
    return store['verdicts'][key]['same']


def link(path: str, store: dict) -> int:
    """Put one day's narratives into threads; how many joined an earlier thread"""
    from app.narratives import embed
    with open(path) as f:
        report = json.load(f)
    day = os.path.basename(path)[7:17]
    told = retold(report)
    since = (date.fromisoformat(day) - timedelta(days=WINDOW)).isoformat()
    past = [t for t in store['threads'].values() if since <= t['days'][-1]['date'] < day]
    joined = 0
    if told and past:
        v = embed([n['claim'] for n in told])
        pv = embed([t['days'][-1]['claim'] for t in past])
        sims = v @ pv.T
    for i, n in enumerate(told):
        entry = dict(n, date=day, report=os.path.basename(path))
        home = None
        if told and past:
            for j in np.argsort(-sims[i])[:CANDIDATES]:
                if sims[i][j] >= CANDIDATE and judge(past[j]['days'][-1]['claim'], n['claim'], store):
                    home = past[j]
                    break
        if home is None:
            tid = f"N{store['next']:04d}"
            store['next'] += 1
            home = store['threads'][tid] = {'id': tid, 'days': []}
        else:
            joined += 1
        home['days'].append(entry)
    store['linked'].append(os.path.basename(path))
    return joined


def link_days() -> dict:
    """Link every day's report not linked yet, oldest first"""
    store = load()
    if llm.backend() is None:
        return store
    for path in day_reports():
        if os.path.basename(path) in store['linked']:
            continue
        joined = link(path, store)
        save(store)
        logger.info("Narrative threads: %s linked, %d told again (%d threads)", os.path.basename(path), joined,
                    len(store['threads']))
    return store


def thread_of(store: dict, report: str, claim: str) -> dict | None:
    """The thread a report's narrative is in"""
    for t in store['threads'].values():
        if any(d['report'] == report and d['claim'] == claim for d in t['days']):
            return t
    return None
