"""Redo the show transcripts made before Oct 20 with Whisper's carry-over (Oct 28, the person: "fuck it yeah").

Before the Oct 20 fix (app/transcribe.py, CARRY = False) a repeated phrase fed itself and Whisper lost most of each
episode: 3.1 characters per second of audio against 15.7 since, and the shows' own transcripts' 15.2. So the shows of
Oct 4-20 gave about 7 claims an episode where whole episodes give about 24. The audio wasn't kept (it never is), but
each episode's address was, and the feeds still serve them.

Two steps, each a step of the experiment queue (scripts/experiments/exp_queue.py, under the GPU lease), each resumable:

    retranscribe.py audio    download each such episode again (one host at a time, HOST_GAP apart), transcribe it as
                             today, and replace its transcript; the old one is kept in BACKUP
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


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('step', choices=['audio', 'claims', 'count'])
    p.add_argument('--limit', type=int, help='at most this many episodes (a trial run)')
    a = p.parse_args()
    if a.step == 'count':
        print(f'{len(todo())} transcripts to redo; {len(redone_urls())} redone')
    else:
        {'audio': audio, 'claims': claims}[a.step](a.limit)
