"""The records group's tables (app/tables/records.py): polls kept and read back for the averages, and the one-time
import of the five JSON files they replaced (scripts/json_import/records.py)."""
import json
import os
from datetime import datetime as dt, UTC

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app import bluesky_examples, polling
from app.analysis import newsiness
from app.models import Base
from app.site import wordcloudgen
from app.tables.records import Poll, PollAnswer
from scripts.json_import import records


@pytest.fixture(autouse=True)
def db(monkeypatch):
    """An in-memory data.db: the data folder is production's"""
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


def poll(id, end, answers, partisan=None, **kw):
    return {'id': id, 'poll_type': 'approval', 'sample_size': 800, 'population': 'rv', 'url': 'https://p',
            'created_at': end, 'start_date': end, 'end_date': end, 'pollster': 'P', 'seat_name': None,
            'sponsors': ['S'], 'internal': False, 'partisan': partisan, 'subject': 'Donald Trump',
            'answers': [{'choice': c, 'pct': v} for c, v in answers.items()], **kw}


def test_polls_replace_the_last_feed_and_read_back_an_answer_a_row(db):
    with db() as s:
        polling.save_polls(s, [poll('old', '2026-01-01', {'Approve': 40})])
        polling.save_polls(s, [poll('a', '2026-10-01', {'Approve': 41, 'Disapprove': 55}),
                               poll('b', '2026-10-02', {'Approve': 44}, partisan='R'),
                               poll('c', '2099-01-01', {'Approve': 90})])  # a typo'd future date
        s.commit()
        assert s.query(Poll).count() == 3 and s.query(PollAnswer).count() == 4
        assert json.loads(s.get(Poll, 'a').sponsors) == ['S']
    df = polling.load_polls()
    assert sorted(zip(df['choice'], df['pct'])) == [('Approve', 41), ('Disapprove', 55)]  # partisan and future out
    assert str(df['end_date'].iloc[0]) == '2026-10-01'


def test_no_polls_is_an_empty_frame():
    assert polling.load_polls().empty


def test_a_fresh_feed_isnt_fetched_again(db, monkeypatch):
    fetched = []

    class Answer:
        def raise_for_status(self):
            pass

        def json(self):
            return [poll('a', '2026-10-01', {'Approve': 41})]
    monkeypatch.setattr(polling.rq, 'get', lambda *a, **kw: fetched.append(1) or Answer())
    polling.fetch_polls()
    polling.fetch_polls()
    assert fetched == [1] and len(polling.load_polls()) == 1


def test_import_reads_each_file_into_its_table(db, tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    uri = 'at://did:plc:a/app.bsky.feed.post/ra'
    files = {
        'polls.json': [poll('a', '2026-10-01', {'Approve': 41, 'Disapprove': 55})],
        'bluesky_examples.json': {
            uri: {'cid': 'c', 'did': 'did:plc:a', 'handle': 'a.bsky.social', 'likes': 30, 'reposts': 1, 'quotes': 0,
                  'replies': 2, 'followers': 9000, 'hidden': False, 'checked': '2026-10-09T08:47:58',
                  'first': '2026-10-07T09:03:21'},
            uri + 'x': {'gone': True, 'checked': '2026-10-09T02:10:48', 'first': '2026-10-07T09:03:21'}},
        'cloud_history.json': [{'at': '2026-10-30T23:05:09', 'words': ['Trump', 'election']},
                               {'at': '2026-10-31T00:07:14', 'words': ['AI']}],
        'scraper_history.json': {'CBC': [{'at': '2026-10-29T17:01', 'url': 'https://cbc.ca', 'found': 20, 'kept': 15,
                                          'added': 0, 'too_long': 0, 'error': None},
                                         {'at': '2026-10-29T18:00', 'url': 'https://cbc.ca', 'found': 0, 'kept': 0,
                                          'added': 0, 'too_long': 0, 'error': 'Timeout'}]},
        'newsiness.json': {'recorded': [{'at': '2026-10-12T23:06:26', 'score': 0.713, 'share': 0.71, 'outlets': 57,
                                         'active': 80, 'story': 358, 'label': 'Omar', 'kind': 'big'}],
                           'reconstructed': [{'at': '2026-10-01T01:00:00', 'score': 0.2, 'share': 0.2, 'outlets': 9,
                                              'active': 70, 'story': None, 'label': '', 'kind': 'slow'}]},
    }
    for name, content in files.items():
        (data / name).write_text(json.dumps(content))
    with db() as s:
        counts = records.run(s, str(data), str(data / 'cache'))
        s.commit()
    assert counts == {'poll': 1, 'bluesky_post': 2, 'cloud_word': 3, 'scraper_run': 2, 'newsiness_point': 2}
    assert all((data / name).exists() for name in files)  # never deleted
    assert bluesky_examples.load() == files['bluesky_examples.json']  # read back in the shape the file had
    assert newsiness.load() == files['newsiness.json']
    assert len(polling.load_polls()) == 2
    from app import scraper_health
    assert scraper_health.past_runs(['CBC'])['CBC'] == files['scraper_history.json']['CBC']
    clouds = wordcloudgen.cloud_history(wordcloudgen.datetime(2026, 10, 30))
    assert [(h['at'].isoformat(), h['words']) for h in clouds] == [(c['at'], c['words']) for c in files['cloud_history.json']]
    # The poll feed counts as fetched when the file was written
    with db() as s:
        written = dt.fromtimestamp(os.path.getmtime(data / 'polls.json'), UTC).replace(tzinfo=None)
        assert abs((s.get(Poll, 'a').fetched - written).total_seconds()) < 1


def test_import_without_the_files_counts_nothing(db, tmp_path):
    with db() as s:
        assert set(records.run(s, str(tmp_path), str(tmp_path / 'cache')).values()) == {0}
