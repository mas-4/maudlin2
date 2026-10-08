"""Everything at a glance, for the checker's 📈 dashboard (Oct 8, the person: "a huge visibility dashboard"): is the
machine keeping up (the hourly runs, problems, the card's heat and load, models loaded again and again), what came in
(headlines, outlets, the side feeds, fact-checks and their pieces, transcripts), what was made of it (claims filed,
waiting, weak, proposals), the motif index, the models' own tests, and the person's curation. Read live from the
database, the data folder and the system's logs, each part again once it's a minute old (the model loads: 15
minutes), in the background (gather())."""
import csv
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td

from app.utils import Config, get_logger
from app.utils.store import read_json

logger = get_logger(__name__)

DAYS = 14
HOURS = 48
OLLAMA_MANIFESTS = '/var/lib/ollama/manifests/registry.ollama.ai/library'


def _db():
    return sqlite3.connect(f'file:{Config.connection_string.removeprefix("sqlite:///")}?mode=ro', uri=True)


def _days(n: int = DAYS) -> list[str]:
    today = dt.now().date()
    return [(today - td(days=i)).isoformat() for i in range(n - 1, -1, -1)]


def _journal(unit: str, hours: int) -> list[str]:
    try:
        out = subprocess.run(['journalctl', '-u', unit, '--since', f'-{hours}h', '--no-pager', '-o', 'short-iso'],
                             capture_output=True, text=True, timeout=30)
        return out.stdout.splitlines()
    except (OSError, subprocess.SubprocessError):
        return []


def runs(hours: int = HOURS) -> list[dict]:
    """The hourly runs: when each started, how long it took, how it ended"""
    out, start = [], None
    for line in _journal('maudlin-scrape.service', hours):
        stamp = line[:19]
        if 'systemd[1]: Starting' in line:
            start = stamp
        elif start and ('systemd[1]: Finished' in line or 'Failed with result' in line):
            minutes = (dt.fromisoformat(stamp) - dt.fromisoformat(start)).total_seconds() / 60
            out.append({'start': start, 'minutes': round(minutes, 1), 'ok': 'Finished' in line})
            start = None
    if start:
        out.append({'start': start, 'minutes': round((dt.now() - dt.fromisoformat(start)).total_seconds() / 60, 1),
                    'ok': None})  # going now
    return out


def _model_names() -> dict:
    """Ollama blob digest -> model name"""
    names = {}
    try:
        for model in os.listdir(OLLAMA_MANIFESTS):
            for tag in os.listdir(os.path.join(OLLAMA_MANIFESTS, model)):
                with open(os.path.join(OLLAMA_MANIFESTS, model, tag)) as f:
                    for layer in json.load(f).get('layers', []):
                        if layer.get('mediaType', '').endswith('.model'):
                            names[layer['digest'].replace(':', '-')[:19]] = f'{model}:{tag}'
    except OSError:
        pass
    return names


def model_loads(hours: int = 24) -> dict:
    """How often each model was loaded into memory, per hour (a model loaded again and again is waiting time)"""
    import re
    names = _model_names()
    by = defaultdict(Counter)
    for line in _journal('ollama', hours):
        if 'loading model via llama-server' in line:
            m = re.search(r'sha256-[0-9a-f]{12}', line)
            if m:
                by[line[:13]][names.get(m.group(0), m.group(0)[:14])] += 1
    return {h: dict(c) for h, c in sorted(by.items())}


def gpu(hours: int = 24) -> list[dict]:
    """The card every ten minutes: temperature, load and power (from the minute log, maudlin-data/gpu_log.csv)"""
    path = os.path.join(Config.data, 'gpu_log.csv')
    since = dt.now() - td(hours=hours)
    buckets = defaultdict(list)
    try:
        with open(path) as f:
            for row in csv.reader(f):
                try:
                    at = dt.strptime(row[0].strip()[:19], '%Y/%m/%d %H:%M:%S')
                except (ValueError, IndexError):
                    continue
                if at >= since:
                    key = at.strftime('%Y-%m-%dT%H:') + f'{at.minute // 10}0'
                    buckets[key].append((float(row[1]), float(row[2].split()[0]), float(row[3].split()[0])))
    except OSError:
        return []
    return [{'at': k, 'temp': round(max(v[0] for v in vs)), 'load': round(sum(v[1] for v in vs) / len(vs)),
             'watts': round(sum(v[2] for v in vs) / len(vs))} for k, vs in sorted(buckets.items())]


def acquisition(con) -> dict:
    """What came in, per day"""
    days = _days()
    since = days[0]

    def per_day(sql):
        return dict(con.execute(sql, (since,)).fetchall())
    from app import sidefeeds
    kind_of = {s['key']: s['kind'] for s in sidefeeds.SOURCES}
    side = defaultdict(Counter)
    for day, source, n in con.execute('SELECT date(first_seen), source, count(*) FROM side_item WHERE first_seen >= ? '
                                      'GROUP BY 1, 2', (since,)):
        side[day][kind_of.get(source, 'other')] += n
    trans = defaultdict(Counter)
    audio = Counter()
    for day, model, n, secs in con.execute('SELECT date(created), model, count(*), sum(seconds) FROM side_transcript '
                                           'WHERE created >= ? GROUP BY 1, 2', (since,)):
        kind = 'from the show' if model == 'published by the show' else 'whisper' if 'whisper' in model else 'failed or skipped'
        trans[day][kind] += n
        audio[day] += (secs or 0) / 3600
    try:
        from app.transcribe import pending
        backlog = len(pending(limit=1000))
    except Exception:  # noqa: BLE001 - the database without side items yet
        backlog = None
    return {
        'days': days,
        'headlines': per_day('SELECT date(first_accessed), count(*) FROM headline WHERE first_accessed >= ? GROUP BY 1'),
        'articles': per_day('SELECT date(first_accessed), count(*) FROM article WHERE first_accessed >= ? GROUP BY 1'),
        'outlets': per_day('SELECT date(last_accessed), count(DISTINCT agency_id) FROM article WHERE last_accessed >= ? GROUP BY 1'),
        'stories': per_day('SELECT date(first_seen), count(*) FROM story WHERE first_seen >= ? GROUP BY 1'),
        'side': {d: dict(side[d]) for d in days}, 'transcripts': {d: dict(trans[d]) for d in days},
        'audio hours': {d: round(audio[d], 1) for d in days}, 'transcription backlog': backlog,
        'outlets in all': con.execute('SELECT count(*) FROM agency').fetchone()[0],
        'feeds in all': len(sidefeeds.SOURCES),
    }


def factchecks() -> dict:
    from app.analysis import factcheck_text, factchecks as fcx
    items = fcx._items(fcx.LABEL_DAYS)
    texts = read_json(factcheck_text.TEXTS, {})
    labels = fcx.load_labels()
    read = Counter((texts.get(i['url']) or {}).get('from', 'not yet') for i in items)
    return {'last 30 days': len(items), 'by checker': dict(Counter(i['source'] for i in items).most_common()),
            'text from': dict(read), 'read from the piece': sum(1 for i in items if (labels.get(i['url']) or {}).get('read') == 'piece'),
            'with a claim': sum(1 for i in items if (labels.get(i['url']) or {}).get('claim'))}


def processing() -> dict:
    """What was made of it: claims filed, waiting, weak; proposals; the shows' episodes"""
    from app import episode_kind
    from app.analysis import filing_confidence as fc, motif_index as mi, motif_proposals as mp, show_claims
    index = mi.load()
    live = mi.live(index)
    unchecked = sum(1 for e in live for c in e['claims'] if not c.get('checked'))
    in_mine = sum(1 for e in live if e.get('done') for c in e['claims'] if not c.get('checked'))
    second = sum(1 for e in live if e.get('done') for c in e['claims']
                 if c.get('checked') == 'yes' and not c.get('rechecked') and c.get('fit') is not None and c['fit'] < 0.5)
    try:
        unfiled = sum(1 for c in mi.searchable_claims() if not c.get('motifs'))
    except Exception:  # noqa: BLE001 - a report or label file missing
        unfiled = None
    proposals = Counter(p['kind'] for p in mp.open_proposals())
    kinds = Counter(episode_kind.load().values())
    return {'unchecked filings': unchecked, 'unchecked in your motifs': in_mine, 'weak, up for a second look': second,
            'claims with no motif': unfiled, 'weak claims with suggestions': len(read_json(fc.ALTERNATIVES, {})),
            'open proposals': dict(proposals), 'episodes': dict(kinds), 'retold on the shows': len(show_claims.kept_retold())}


def motifs() -> dict:
    from app.analysis import motif_index as mi
    index = mi.load()
    live = [e for e in mi.live(index) if e['claims']]
    groups = index.get('groups', {})
    by_group = Counter(groups.get(g, {}).get('name', g) for e in live for g in mi.person_groups(e))
    by_genre = Counter(mi.person_genre(e) or 'no genre yet' for e in live)
    week = (dt.now() - td(days=7)).date().isoformat()
    growing = Counter()
    for e in live:
        growing[e['name']] = sum(1 for c in e['claims'] if (c.get('date') or '') >= week)
    history = mi.metrics_history()
    return {'now': history['now'], 'days': history['days'], 'by genre': dict(by_genre.most_common()),
            'by group': dict(by_group.most_common(25)), 'growing this week': growing.most_common(12),
            'biggest': [(e['name'], len(e['claims'])) for e in sorted(live, key=lambda e: -len(e['claims']))[:12]],
            'newest': [(e['name'], e.get('first_seen', '')) for e in sorted(live, key=lambda e: e.get('first_seen') or '')[-10:]][::-1]}


def models() -> dict:
    from app.analysis import filing_confidence as fc, motif_retriever as mr, reranker_teach
    m = read_json(fc.MODEL, None) or {}
    t = m.get('test') or {}
    sure = next((r for r in t.get('thresholds', []) if r['at'] == t.get('sure_at')), None)
    learned = read_json(mr.LEARNED, None) or {}
    w = read_json(mr.WEIGHTS, None) or {}
    results = []
    try:
        with open(os.path.join(Config.data, 'motifs', 'experiments', 'results.log')) as f:
            results = [x.strip() for x in f.readlines()[-14:]]
    except OSError:
        pass
    return {'confidence': {'at': m.get('at'), 'auc': t.get('auc'), 'sure at': t.get('sure_at'),
                           'kept passable when sure': sure and sure.get('of kept'), 'precision when sure': sure and sure.get('precision'),
                           'decisions': t.get('filings'), 'reranker': m.get('reranker', 'base')},
            'shortlist': {'at': learned.get('at'), **(learned.get('test') or {}), 'claims': learned.get('claims'),
                          'plain weights at': w.get('at')},
            'reranker': read_json(reranker_teach.META, {}) or {'at': 'not taught yet'},
            'experiments': results}


def curation(days: int = DAYS) -> dict:
    from app.analysis import curation_db
    first = _days(days)[0]
    per = defaultdict(Counter)
    kinds = Counter()
    week = (dt.now() - td(days=7)).isoformat()
    for a in curation_db.actions():
        day = (a.get('at') or '')[:10]
        if day < first:
            continue
        who = 'claude' if a.get('by') == 'claude' else 'you'
        per[day][who] += 1
        if who == 'you' and (a.get('at') or '') >= week:
            act = a.get('action') or {}
            for step in act.get('steps', [act]) if act.get('action') == 'batch' else [act]:
                kinds[step.get('action', '?')] += 1
    return {'per day': {d: dict(per[d]) for d in _days(days)}, 'this week by kind': dict(kinds.most_common())}


def machine() -> dict:
    disk = shutil.disk_usage(Config.data)
    sizes = {}
    for name in ('data.db', 'curation.sqlite', 'motif_index.json'):
        p = os.path.join(Config.data, name)
        if os.path.exists(p):
            sizes[name] = round(os.path.getsize(p) / 1e6, 1)
    return {'disk free GB': round(disk.free / 1e9, 1), 'disk used %': round(100 * disk.used / disk.total),
            'files MB': sizes, 'health': read_json(os.path.join(Config.data, 'health.json'), None)}


TTL = {'model loads': 900, 'processing': 120}  # seconds a part is kept (the rest: a minute); counting the model loads
# reads a day of Ollama's log, ten seconds or more
_parts = {}  # name -> (when worked out, its data)
_lock = threading.Lock()
_refreshing = threading.Event()


def _acquisition():
    con = _db()
    try:
        return acquisition(con)
    finally:
        con.close()


PARTS = {'runs': runs, 'model loads': model_loads, 'gpu': gpu, 'acquisition': _acquisition, 'fact-checks': factchecks,
         'processing': processing, 'motifs': motifs, 'models': models, 'curation': curation, 'machine': machine}


def _refresh(force: bool = False):
    for name, fn in PARTS.items():
        at, _ = _parts.get(name, (0, None))
        if force or time.time() - at > TTL.get(name, 60):
            try:
                data = fn()
            except Exception as e:  # noqa: BLE001 - one part failing shows as such; the rest still shows
                logger.warning("Dashboard: %s failed (%s)", name, e)
                data = {'error': f'{type(e).__name__}: {e}'}
            with _lock:
                _parts[name] = (time.time(), data)


def gather(fresh: bool = False) -> dict:
    """The whole dashboard: worked out in full the first time (or when `fresh`); after that, the latest at once, with
    whatever has gone stale worked out again in the background"""
    if fresh or len(_parts) < len(PARTS):
        _refresh(force=fresh)
    elif not _refreshing.is_set():
        _refreshing.set()

        def run():
            try:
                _refresh()
            finally:
                _refreshing.clear()
        threading.Thread(target=run, daemon=True).start()
    with _lock:
        out = {name: data for name, (_, data) in _parts.items()}
        out['at'] = dt.fromtimestamp(min(at for at, _ in _parts.values())).isoformat(timespec='seconds')
    return out
