"""Narratives across days: the layers above single posts (#142 follow-up). Posts that tell one thing make a day's group
(a narrative in one day's report, app/narratives.py); the same narrative told again on later days makes a thread,
followed across days like a saga (app/analysis/sagas.py) follows a news story across its parts.

Each day's report (the latest of the day that covers at least six hours) is linked once: each narrative is compared
by meaning with the threads seen in the last WINDOW days, and the closest few are put to the bigger local model, which
says whether it is the same narrative told again or a different one. A narrative with no match starts a thread."""
import os
from datetime import date, timedelta

import numpy as np

from app.analysis import llm
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json
from app.analysis import local_models

logger = get_logger(__name__)

WINDOW = 14  # days a thread waits to be told again
CANDIDATE = 0.7  # a thread at least this alike (mxbai) is put to the model
CANDIDATES = 3
MIN_HOURS = 6  # reports covering less (early trials) aren't a day
MODEL = local_models.BIG  # Oct 6 test: 18 of 21 retold found, 1 of 9 wrongly joined, the same both runs (30B: 15-17, 1)
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


def verdicts_path() -> str:
    """The model's same-or-different answers: a cache, asked again if lost"""
    return os.path.join(Config.cache, 'narratives', 'thread_verdicts.json')


def load() -> dict:
    """{'next': the next thread's number, 'threads': {id: {id, days: [...]}}, 'linked': [report], 'verdicts': {...}}"""
    from app.models import Session
    from app.tables.narratives import NarrativeReport, NarrativeThreadDay
    threads = {}
    with Session() as s:
        for d in s.query(NarrativeThreadDay).order_by(NarrativeThreadDay.id):
            threads.setdefault(d.thread, {'id': d.thread, 'days': []})['days'].append(
                {'claim': d.claim, 'people': d.people, 'posts': d.posts, 'genre': d.genre, 'story': d.story,
                 'date': d.date, 'report': d.report})
        linked = sorted(f for (f,) in s.query(NarrativeReport.file).filter(NarrativeReport.threads_linked))
    last = max((int(t[1:]) for t in threads if t[1:].isdigit()), default=0)
    return {'next': last + 1, 'threads': threads, 'linked': linked, 'verdicts': read_json(verdicts_path(), {})}


def day_reports() -> list[str]:
    """The report of each day (the latest that covers at least MIN_HOURS), oldest first"""
    from app.models import Session
    from app.tables.narratives import NarrativeReport
    by_day = {}
    with Session() as s:
        for (file,) in s.query(NarrativeReport.file).filter(NarrativeReport.hours >= MIN_HOURS) \
                .order_by(NarrativeReport.file):
            by_day[file[7:17]] = file
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


def link(file: str, store: dict) -> int:
    """Put one day's narratives into threads, kept at once; how many joined an earlier thread"""
    from app.models import Session
    from app.narratives import embed, load_report
    from app.tables.narratives import NarrativeReport, NarrativeThreadDay
    report = load_report(file) or {'found': []}
    day = file[7:17]
    told = retold(report)
    since = (date.fromisoformat(day) - timedelta(days=WINDOW)).isoformat()
    past = [t for t in store['threads'].values() if since <= t['days'][-1]['date'] < day]
    joined = 0
    if told and past:
        v = embed([n['claim'] for n in told])
        pv = embed([t['days'][-1]['claim'] for t in past])
        sims = v @ pv.T
    added = []
    for i, n in enumerate(told):
        entry = dict(n, date=day, report=file)
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
        added.append(NarrativeThreadDay(thread=home['id'], **entry))
    write_json(verdicts_path(), store['verdicts'])
    with Session() as s:  # the day's entries and its mark together: a day is linked whole or not at all
        s.add_all(added)
        s.query(NarrativeReport).filter(NarrativeReport.file == file).update({'threads_linked': True})
        s.commit()
    store['linked'].append(file)
    return joined


def link_days() -> dict:
    """Link every day's report not linked yet, oldest first"""
    store = load()
    if llm.backend() is None:
        return store
    for file in day_reports():
        if file in store['linked']:
            continue
        joined = link(file, store)
        logger.info("Narrative threads: %s linked, %d told again (%d threads)", file, joined, len(store['threads']))
    return store


def thread_of(store: dict, report: str, claim: str) -> dict | None:
    """The thread a report's narrative is in"""
    for t in store['threads'].values():
        if any(d['report'] == report and d['claim'] == claim for d in t['days']):
            return t
    return None
