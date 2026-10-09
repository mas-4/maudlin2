"""app/transcribe.py: ad trimming, the queue and storage, with a fake model and fake downloads (no GPU, no network)."""
import json
import subprocess
from datetime import datetime as dt, timedelta as td
from types import SimpleNamespace

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.transcribe as tr
from app.models import Base, SideItem, SideTranscript


def seg(start, text):
    return {'start': start, 'end': start + 3, 'text': text}


def test_trim_ads_start_and_end():
    segments = [seg(0, 'This message comes from Capital One with the Venture X card.'),
                seg(4, 'Earn unlimited double miles.'), seg(8, 'Cash Plus. Terms apply.'),
                seg(14, 'This is NPR News Now.'), seg(60, 'The story.'), seg(300, 'More news.'),
                seg(330, 'Support for NPR comes from listeners like you.')]
    kept = tr.trim_ads(segments)
    assert [k['text'] for k in kept] == ['This is NPR News Now.', 'The story.', 'More news.']


def test_trim_ads_keeps_clean_transcripts_and_mid_rolls():
    segments = [seg(0, 'Good morning.'), seg(100, 'Support for this podcast comes from X.'), seg(200, 'Bye.')]
    assert tr.trim_ads(segments) == segments
    assert tr.trim_ads([]) == []


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(tr, 'Session', session)
    import app.sidefeeds as sf
    monkeypatch.setattr(sf, 'Session', session)
    return session


def add(session, source, hours_ago, audio='https://a/x.mp3'):
    now = dt.utcnow()
    with session() as s:
        item = SideItem(source=source, title=f'{source} {hours_ago}', url=f'{source}-{hours_ago}', audio=audio,
                        published=now - td(hours=hours_ago), first_seen=now)
        s.add(item)
        s.commit()
        return item.id


def test_pending_order_and_filters(db):
    show = add(db, 'remnant', 1)
    newscast = add(db, 'nprnewsnow', 5)
    published = add(db, 'psa', 2)
    caller = add(db, 'jessekelly', 4)  # ordinary voices come before the long shows
    add(db, 'psa', 24 * 5)  # too old
    add(db, 'psa', 3, audio=None)  # no audio
    assert [i.id for i in tr.pending()] == [newscast, published, caller, show]


def test_transcribe_pending_stores_and_skips_done(db, monkeypatch):
    item = add(db, 'nprnewsnow', 1)
    monkeypatch.setattr(tr, 'free_gpu', lambda: True)
    monkeypatch.setattr(tr, 'PAUSE', 0)
    monkeypatch.setattr(tr, 'download', lambda url, folder: 'unused')
    monkeypatch.setattr(tr, 'decode', lambda path: np.zeros(16000 * 10, np.float32))
    segments = [SimpleNamespace(start=0.0, end=2.0, text=' Terms apply.'),
                SimpleNamespace(start=3.0, end=6.0, text=' This is NPR News Now.')]
    monkeypatch.setattr(tr, 'model', lambda: SimpleNamespace(transcribe=lambda audio, **kw: (iter(segments), None)))
    assert tr.transcribe_pending(budget=60) == 1
    with db() as s:
        [t] = s.query(SideTranscript).all()
        assert t.item_id == item and t.model == tr.JUDGE and t.seconds == 10
        assert t.text == 'This is NPR News Now.'
        assert json.loads(t.segments)[0]['start'] == 3.0
    assert tr.transcribe_pending(budget=60) == 0  # nothing left


def test_too_big_and_failed_items_are_recorded_not_retried(db, monkeypatch):
    add(db, 'nprnewsnow', 1)
    add(db, 'psa', 2)
    monkeypatch.setattr(tr, 'free_gpu', lambda: True)
    monkeypatch.setattr(tr, 'PAUSE', 0)

    def download(url, folder):
        if download.calls:
            raise subprocess.CalledProcessError(1, 'ffmpeg')  # unreadable audio: won't get better
        download.calls += 1
        return None  # the first is too big
    download.calls = 0
    monkeypatch.setattr(tr, 'download', download)
    assert tr.transcribe_pending(budget=60) == 0
    with db() as s:
        assert sorted(t.model for t in s.query(SideTranscript)) == ['failed: CalledProcessError',
                                                                     'skipped: over the size limit']
    assert tr.pending() == []


def test_out_of_memory_is_not_recorded_and_stops_the_round(db, monkeypatch):
    add(db, 'nprnewsnow', 1)
    add(db, 'nprnewsnow', 2)
    monkeypatch.setattr(tr, 'free_gpu', lambda: True)
    monkeypatch.setattr(tr, 'PAUSE', 0)
    calls = []

    def download(url, folder):
        calls.append(url)
        raise RuntimeError('CUDA failed with error out of memory')
    monkeypatch.setattr(tr, 'download', download)
    assert tr.transcribe_pending(budget=60) == 0
    assert len(calls) == 1  # stopped after the first
    with db() as s:
        assert s.query(SideTranscript).count() == 0
    assert len(tr.pending()) == 2  # both wait for the next run


def test_the_next_episode_downloads_while_one_is_transcribed(db, monkeypatch):
    add(db, 'nprnewsnow', 1)
    add(db, 'nprnewsnow', 2)
    monkeypatch.setattr(tr, 'free_gpu', lambda: True)
    monkeypatch.setattr(tr, 'PAUSE', 0)
    import threading
    second = threading.Event()
    calls = []

    def download(url, folder):
        calls.append(url)
        if len(calls) == 2:
            second.set()
        return 'unused'
    monkeypatch.setattr(tr, 'download', download)
    monkeypatch.setattr(tr, 'decode', lambda path: np.zeros(16000, np.float32))
    overlapped = []

    def transcribe(audio, **kw):
        overlapped.append(second.wait(timeout=5))  # the first one's transcription waits for the second's download
        return iter([SimpleNamespace(start=0.0, end=1.0, text=' Hello.')]), None
    monkeypatch.setattr(tr, 'model', lambda: SimpleNamespace(transcribe=transcribe))
    assert tr.transcribe_pending(budget=60) == 2
    assert overlapped[0] and len(calls) == 2


def test_busy_gpu_skips_the_round(db, monkeypatch):
    add(db, 'nprnewsnow', 1)
    monkeypatch.setattr(tr, 'free_gpu', lambda: False)
    monkeypatch.setattr(tr, 'download', lambda url, folder: pytest.fail('should not download'))
    assert tr.transcribe_pending(budget=60) == 0


def test_permanent_errors():
    response = SimpleNamespace(status_code=404)
    assert tr.permanent(type('E', (Exception,), {'response': response})('gone'))
    assert not tr.permanent(RuntimeError('CUDA failed with error out of memory'))
    assert not tr.permanent(tr.rq.ConnectionError('offline'))
