"""The narratives group in data.db: reports and their groups, withheld claims, threads, matched TV captions, and the
one-time import of their JSON files."""
import json
from datetime import datetime as dt, timedelta as td

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app import chyrons, narratives
from app.tables.narratives import ChyronMatch, NarrativeGroup, NarrativeReport, NarrativeThreadDay


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session


REPORT = {'made': '2026-10-05T08:17', 'hours': 24, 'posts': 900, 'authors': 700, 'groups': 3,
          'kinds': {'told': 2, 'copypasta': 1}, 'focus_group_segments': 4,
          'found': [{'posts': 20, 'authors': 18, 'variety': 0.9, 'kind': 'told', 'replies': 0.1, 'about': None,
                     'shared': [['https://a/1', 3]], 'sources': {'bluesky': 20}, 'examples': ['one', 'two'],
                     'label': {'narrative': 'The count was rigged', 'retold': True, 'genre': 'rumor', 'motif': 'm'},
                     'story': {'label': 'Election', 'relation': 'same event', 'id': 12}, 'keys': ['k1', 'k2']},
                    {'posts': 9, 'authors': 8, 'variety': 0.6, 'kind': 'told', 'replies': 0.0, 'shared': [],
                     'sources': {}, 'examples': ['x'], 'label': None, 'story': None},
                    {'posts': 7, 'authors': 6, 'variety': 0.1, 'kind': 'copypasta', 'replies': 0.0, 'shared': [],
                     'sources': {'mastodon': 7}, 'examples': ['same words']}]}


def test_a_report_comes_back_as_it_was_written(db):
    narratives.save_report('report-2026-10-05-0817.json', REPORT)
    got = narratives.load_report('report-2026-10-05-0817.json')
    assert got.pop('file') == 'report-2026-10-05-0817.json'
    assert got == REPORT
    # None and missing stay apart: a label the model didn't give, and a copypasta group never labeled
    assert got['found'][1]['label'] is None and 'label' not in got['found'][2]
    with db() as s:
        first = s.query(NarrativeGroup).filter_by(position=0).one()
        assert (first.narrative, first.retold, first.story_id) == ('The count was rigged', True, 12)


def test_saving_a_report_again_replaces_it(db):
    narratives.save_report('report-2026-10-05-0817.json', REPORT)
    narratives.save_report('report-2026-10-05-0817.json', dict(REPORT, found=REPORT['found'][:1]))
    assert len(narratives.load_report('report-2026-10-05-0817.json')['found']) == 1
    with db() as s:
        assert s.query(NarrativeGroup).count() == 1 and s.query(NarrativeReport).count() == 1


def test_reports_in_order_latest_and_named(db):
    assert narratives.latest_report() is None and narratives.reports() == []
    for stamp in ('2026-10-06-0439', '2026-10-04-1344', '2026-10-05-0817'):
        narratives.save_report(f'report-{stamp}.json', {'made': stamp, 'hours': 24, 'found': []})
    assert narratives.report_files() == ['report-2026-10-04-1344.json', 'report-2026-10-05-0817.json',
                                         'report-2026-10-06-0439.json']
    assert narratives.latest_report()['made'] == '2026-10-06-0439'
    assert [r['made'] for r in narratives.reports(newest_first=True)][0] == '2026-10-06-0439'
    assert [r['made'] for r in narratives.reports(['report-2026-10-05-0817.json'])] == ['2026-10-05-0817']


def test_reports_by_day_takes_each_days_last_report(db):
    from app.site import page_story
    today, old = dt.now().strftime('%Y-%m-%d'), (dt.now() - td(days=30)).strftime('%Y-%m-%d')
    for name in (f'report-{today}-0400.json', f'report-{today}-1400.json', f'report-{old}-0400.json'):
        narratives.save_report(name, {'made': name, 'found': []})
    assert [r['file'] for r in page_story.reports_by_day()] == [f'report-{today}-1400.json']


def test_withheld_claims(db):
    assert narratives.withheld() == set()
    narratives.withhold('A misread claim', 'one post quoted it')
    narratives.withhold('A misread claim', 'said again')  # once, the latest reason
    assert narratives.withheld() == {'A misread claim'}


def test_matched_captions_by_day(db, monkeypatch):
    cap = lambda at, text, **kw: {'at': at, 'channel': 'CNNW', 'seconds': 30, 'program': 'News', 'text': text, **kw}  # noqa: E731
    chyrons.save_matched('2026-10-04', [cap('2026-10-04T10:00:00', 'OLD')])
    chyrons.save_matched('2026-10-05', [cap('2026-10-05T10:00:00', 'STALE')])
    chyrons.save_matched('2026-10-05', [cap('2026-10-05T10:00:00', 'A', story=7, label='Storm', rank=1, outlets=9),
                                        cap('2026-10-05T11:00:00', 'B')])  # the day matched again: replaced
    chyrons.save_matched('2026-10-06', [cap('2026-10-06T09:00:00', 'C')])
    assert [c['text'] for c in chyrons.matched()] == ['OLD', 'A', 'B', 'C']
    assert [c['text'] for c in chyrons.matched(2)] == ['A', 'B', 'C']
    a = chyrons.matched(2)[0]
    assert a == cap('2026-10-05T10:00:00', 'A', story=7, label='Storm', rank=1, outlets=9)
    from app.analysis import motif_web
    from app.site import page_story, page_tv
    assert page_tv.matched(1)[0]['at'] == dt(2026, 10, 6, 9)
    assert motif_web.recent_captions(1) == [('C', 'CNN')]
    monkeypatch.setattr(page_story, 'story_merges', dict)
    assert page_story.tv_by_story()[7]['captions'][0]['text'] == 'A'


def test_the_import_reads_every_file(db, tmp_path, monkeypatch):
    from scripts.json_import import narratives as imp
    data, cache = tmp_path / 'data', tmp_path / 'data' / 'cache'
    (data / 'narratives').mkdir(parents=True)
    (data / 'chyrons').mkdir()
    (data / 'narratives' / 'report-2026-10-05-0817.json').write_text(json.dumps(REPORT))
    (data / 'narratives' / 'report-2026-10-05-0817.md').write_text('# left alone')
    (data / 'narratives' / 'withheld.json').write_text(json.dumps([{'claim': 'A misread', 'reason': 'r', 'at': '2026-10-04'}]))
    (data / 'narratives' / 'threads.json').write_text(json.dumps({
        'next': 3, 'linked': ['report-2026-10-05-0817.json', 'report-gone.json'],
        'threads': {'N0001': {'id': 'N0001', 'days': [{'claim': 'c', 'people': 5, 'posts': 6, 'genre': 'rumor', 'story': None,
                                                       'date': '2026-10-05', 'report': 'report-2026-10-05-0817.json'}]},
                    'N0002': {'id': 'N0002', 'days': [{'claim': 'd', 'people': 5, 'posts': 5, 'genre': 'rumor', 'story': 'S',
                                                       'date': '2026-10-05', 'report': 'report-2026-10-05-0817.json'}]}},
        'verdicts': {'a\nb': {'same': True, 'reason': 'r'}}}))
    (data / 'chyrons' / 'matched-2026-10-05.json').write_text(json.dumps([
        {'at': '2026-10-05T10:00:00', 'channel': 'CNNW', 'seconds': 30, 'program': 'News', 'text': 'A', 'story': 7,
         'label': 'Storm', 'rank': 1, 'outlets': 9}]))
    with db() as s:
        counts = imp.run(s, str(data), str(cache))
        s.commit()
    assert counts == {'reports': 1, 'groups': 3, 'withheld': 1, 'thread_days': 2, 'linked': 1, 'verdicts': 1,
                      'chyron_days': 1, 'chyron_matches': 1}
    got = narratives.load_report('report-2026-10-05-0817.json')
    got.pop('file')
    assert got == REPORT and narratives.withheld() == {'A misread'}
    from app.analysis import narrative_threads as nt
    from app.utils import Config
    monkeypatch.setattr(Config, 'cache', str(cache))
    store = nt.load()
    assert store['next'] == 3 and store['linked'] == ['report-2026-10-05-0817.json']
    assert store['threads']['N0002']['days'][0]['story'] == 'S' and store['verdicts'] == {'a\nb': {'same': True, 'reason': 'r'}}
    assert chyrons.matched()[0]['story'] == 7
    assert (data / 'narratives' / 'threads.json').exists() and (data / 'narratives' / 'report-2026-10-05-0817.md').exists()
    with db() as s:
        assert s.query(NarrativeThreadDay).count() == 2 and s.query(ChyronMatch).count() == 1


def test_the_import_with_nothing_there(db, tmp_path):
    from scripts.json_import import narratives as imp
    with db() as s:
        assert set(imp.run(s, str(tmp_path), str(tmp_path / 'cache')).values()) == {0}
