"""Redo the show transcripts made before Oct 20 with Whisper's carry-over (Oct 28, the person: "fuck it yeah").

Before the Oct 20 fix (app/transcribe.py, CARRY = False) a repeated phrase fed itself and Whisper lost most of each
episode: 3.1 characters per second of audio against 15.7 since, and the shows' own transcripts' 15.2. So the shows of
Oct 4-20 gave about 7 claims an episode where whole episodes give about 24. The audio wasn't kept (it never is), but
each episode's address was, and the feeds still serve them.

Two steps, each a step of the experiment queue (scripts/experiments/exp_queue.py, under the GPU lease), each resumable:

    retranscribe.py audio    download each such episode again (one host at a time, HOST_GAP apart), transcribe it as
                             today, and replace its transcript; the old one is kept in BACKUP
    retranscribe.py carryover  episodes redone on the lab copy brought into production (Oct 28)
    retranscribe.py claims   read the redone episodes' claims again (show_claims.read_part, as the hourly reader does)
                             and add the ones the episode didn't already have (mxbai, SIMILAR to an old one: the same
                             claim); old claims stay, so nothing filed or checked loses its telling

The grouping into retold claims and the filing work over every episode on their next run, with no date window."""
import argparse
import json
import os
import sys
import tempfile
import time
from datetime import datetime as dt
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from app.utils import Config, get_logger  # noqa: E402

logger = get_logger(__name__)

OLD = 'faster-whisper large-v3-turbo int8_float16'  # the carry-over transcripts' label
SKIP = {'nprnewsnow', 'abcupdate', 'bloombergnow', 'focusgroup'}  # newscasts and focus groups: not read for claims
HOST_GAP = 15  # seconds between downloads from one host
BACKUP = os.path.join(Config.data, 'transcripts_carryover.jsonl')  # the replaced transcripts, one JSON line each
FAILED = os.path.join(Config.data, 'retranscribe_failed.json')  # item id -> why it can't be redone
DONE_CLAIMS = os.path.join(Config.data, 'retranscribe_claims.json')  # episode url -> when its claims were read again
SIMILAR = 0.84  # show_claims.SIMILARITY: two show claims this alike are one claim


def todo() -> list:
    """The carry-over show transcripts still to redo: (transcript row id, item id, source, title, audio url), newest
    first"""
    from app.models import Session, SideItem, SideTranscript
    failed = read(FAILED, {})
    with Session() as s:
        rows = s.query(SideTranscript.id, SideItem.id, SideItem.source, SideItem.title, SideItem.audio).join(
            SideItem, SideItem.id == SideTranscript.item_id).filter(
            SideTranscript.model == OLD, SideItem.source.notin_(SKIP), SideItem.audio.isnot(None)).order_by(
            SideItem.published.desc()).all()
    return [r for r in rows if str(r[1]) not in failed]


def read(path: str, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write(path: str, data):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def audio(limit: int | None = None):
    from app import transcribe as tr
    from app.models import Session, SideTranscript, SqlLock
    rows = todo()[:limit]
    print(f'retranscribe: {len(rows)} episodes to redo', flush=True)
    if not rows or not tr.free_gpu():
        return
    words, last, failed = tr.hotwords(), {}, read(FAILED, {})
    for n, (tid, item_id, source, title, url) in enumerate(rows, 1):
        host = urlparse(url).netloc
        wait = HOST_GAP - (time.time() - last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        last[host] = time.time()
        try:
            with tempfile.TemporaryDirectory(prefix='maudlin-redo-') as folder:
                path = tr.download(url, folder)
                if path is None:
                    failed[str(item_id)] = 'over the size limit'
                    write(FAILED, failed)
                    continue
                sound = tr.decode(path)
            segments, _ = tr.model().transcribe(sound, language='en', vad_filter=True, beam_size=1, hotwords=words,
                                                condition_on_previous_text=tr.CARRY)
            kept = tr.trim_ads([{'start': round(x.start, 1), 'end': round(x.end, 1), 'text': tr.fix_text(x.text.strip())}
                                for x in segments])
        except Exception as e:  # noqa: BLE001 - one bad file mustn't stop the rest
            if tr.permanent(e):
                failed[str(item_id)] = f'{type(e).__name__}: {e}'[:200]
                write(FAILED, failed)
                print(f'retranscribe: {n}/{len(rows)} {source} failed for good: {e}', flush=True)
                continue
            raise  # out of memory or offline: the queue tries the step again later
        with Session() as s, SqlLock:
            row = s.get(SideTranscript, tid)
            with open(BACKUP, 'a', encoding='utf-8') as f:
                f.write(json.dumps({'item_id': item_id, 'model': row.model, 'created': str(row.created),
                                    'seconds': row.seconds, 'text': row.text, 'segments': row.segments}) + '\n')
            before = len(row.text or '')
            row.model, row.created = tr.JUDGE, dt.utcnow()
            row.seconds = len(sound) / 16000
            row.text = ' '.join(x['text'] for x in kept)
            row.segments = json.dumps(kept)
            s.commit()
            after = len(row.text)
        print(f'retranscribe: {n}/{len(rows)} {source} "{title[:60]}" {before} -> {after} chars', flush=True)


def claims(limit: int | None = None):
    from app.analysis import llm, show_claims as sc
    from app.narratives import embed
    import numpy as np
    store, done = sc.load(), read(DONE_CLAIMS, {})
    redone = redone_urls()
    eps = [ep for ep in sc.episodes(days=60) if ep['url'] in redone and ep['url'] not in done][:limit]
    print(f'retranscribe claims: {len(eps)} episodes to read again', flush=True)
    for n, ep in enumerate(eps, 1):
        entry = store.setdefault(ep['url'], {k: ep[k] for k in ('source', 'show', 'lean', 'title', 'date')} |
                                 {'read': 0, 'claims': []})
        found = []
        for kept, _dropped in llm.parallel(lambda chunk, ep=ep: sc.read_part(ep, chunk), ep["chunks"]):
            found += kept
        old = entry.get('claims', [])
        if old and found:
            sims = embed([c['claim'] for c in found]) @ embed([c['claim'] for c in old]).T
            new = [c for c, row in zip(found, sims) if float(np.max(row)) < SIMILAR]
        else:
            new = found
        store = sc.load()  # the hourly reader may have saved meanwhile
        entry = store.setdefault(ep['url'], entry)
        entry['claims'] = entry.get('claims', []) + [dict(c, reread='2026-10-28') for c in new]
        entry['chunks'] = entry['read'] = len(ep['chunks'])
        sc.save(store)
        done[ep['url']] = {'at': dt.utcnow().isoformat(timespec='seconds'), 'found': len(found), 'added': len(new)}
        write(DONE_CLAIMS, done)
        print(f'retranscribe claims: {n}/{len(eps)} {ep["show"]} +{len(new)} of {len(found)}', flush=True)


def carryover() -> int:
    """Episodes redone on the lab copy (where the experiment queue put this job until Oct 28) brought into production:
    each production transcript still on the old model takes the lab's new one, its old text appended to BACKUP first,
    as audio() does. Idempotent: rows production has already redone are left alone"""
    import sqlite3
    lab_db, lab_backup = os.path.join(LAB, 'data', 'data.db'), os.path.join(LAB, 'data', 'transcripts_carryover.jsonl')
    if not (os.path.exists(lab_db) and os.path.exists(lab_backup)):
        print('retranscribe carryover: no lab copy to carry over', flush=True)
        return 0
    with open(lab_backup, encoding='utf-8') as f:
        redone = {json.loads(line)['item_id'] for line in f if line.strip()}
    lab = sqlite3.connect(f'file:{lab_db}?mode=ro', uri=True)
    new = {r[0]: r[1:] for r in lab.execute('select item_id, model, created, seconds, text, segments from side_transcript '
                                             'where model != ?', (OLD,)) if r[0] in redone}
    prod = sqlite3.connect(Config.db_file_path, timeout=300)
    moved = 0
    prod.execute('begin immediate')
    with open(BACKUP, 'a', encoding='utf-8') as out:
        for item, (model, created, seconds, text, segments) in new.items():
            row = prod.execute('select id, model, created, seconds, text, segments from side_transcript where item_id = ?',
                               (item,)).fetchone()
            if not row or row[1] != OLD:
                continue
            out.write(json.dumps({'item_id': item, 'model': row[1], 'created': str(row[2]), 'seconds': row[3],
                                  'text': row[4], 'segments': row[5]}) + '\n')
            prod.execute('update side_transcript set model = ?, created = ?, seconds = ?, text = ?, segments = ? '
                         'where id = ?', (model, created, seconds, text, segments, row[0]))
            moved += 1
    prod.commit()
    print(f'retranscribe carryover: {len(new)} redone on the lab copy, {moved} new to production', flush=True)
    return moved


def redone_urls() -> set:
    """The episodes whose carry-over transcript was replaced (BACKUP)"""
    from app.models import Session, SideItem
    ids = set()
    if os.path.exists(BACKUP):
        with open(BACKUP, encoding='utf-8') as f:
            ids = {json.loads(line)['item_id'] for line in f if line.strip()}
    if not ids:
        return set()
    with Session() as s:
        return {u for (u,) in s.query(SideItem.url).filter(SideItem.id.in_(ids))}


LAB = os.path.expanduser('~/maudlin-lab')  # the experiments' copy of the data (scripts/experiments/lab_data.py)


if __name__ == '__main__':
    # This job fixes production's transcripts, so it runs on production's data even from the experiment queue, which
    # points every step at the lab copy: queue it as `env MAUDLIN_DATA=~/maudlin-data ...` (Oct 28: 223 episodes were
    # redone on the lab copy before anyone noticed, then carried over by hand)
    if os.path.realpath(Config.data).startswith(os.path.realpath(LAB)):
        sys.exit('retranscribe: refusing to run on the lab copy of the data; set MAUDLIN_DATA to production\'s')
    p = argparse.ArgumentParser()
    p.add_argument('step', choices=['audio', 'claims', 'count', 'carryover'])
    p.add_argument('--limit', type=int, help='at most this many episodes (a trial run)')
    a = p.parse_args()
    if a.step == 'carryover':
        carryover()
    elif a.step == 'count':
        print(f'{len(todo())} transcripts to redo; {len(redone_urls())} redone')
    else:
        {'audio': audio, 'claims': claims}[a.step](a.limit)
