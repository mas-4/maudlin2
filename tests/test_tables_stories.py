"""The stories group's tables (app/tables/stories.py): merges, splits, label times, ended sagas, saga pair verdicts,
the story pages' extras and the name aliases, through the code that reads and writes them, and the one-time import of
their JSON files (scripts/json_import/stories.py)."""
import json
from datetime import datetime as dt, timedelta as td
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models as models
from app.models import Base, Saga, Story
from app.tables import stories as t


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    from app.analysis import sagas, stories
    monkeypatch.setattr(stories, 'Session', session)
    monkeypatch.setattr(sagas, 'Session', session)
    return session


def test_a_merge_is_remembered_and_its_saga_of_one_ends(db):
    from app.analysis import sagas, stories
    with db() as s:
        s.add(Saga(id=5, first_seen=dt(2026, 10, 1), last_seen=dt(2026, 10, 2)))
        s.add_all([Story(id=1, label='Kept', first_seen=dt(2026, 10, 1), last_seen=dt(2026, 10, 2), saga_id=5),
                   Story(id=2, label='Gone', first_seen=dt(2026, 10, 2), last_seen=dt(2026, 10, 3), saga_id=5)])
        s.commit()
    stories.merge_stories(1, 2, why='the same event')
    assert stories.merges() == {2: 1}
    with db() as s:
        row = s.get(t.StoryMerge, 2)
        assert (row.label, row.why, row.first_seen) == ('Gone', 'the same event', dt(2026, 10, 2))
        assert s.get(Saga, 5) is None
    assert sagas.ended() == {5: {'story': 1}}


def test_ended_sagas_point_on_and_their_ids_are_never_reused(db):
    from app.analysis import sagas
    sagas.record_end(17, {'story': 136})
    sagas.record_end(3, {'saga': 1})
    sagas.record_end(2, {})
    sagas.record_end(3, {'saga': 9})  # absorbed again: points on to the newer
    assert sagas.ended() == {17: {'story': 136}, 3: {'saga': 9}, 2: {}}
    with db() as s:
        s.add(Saga(id=4, first_seen=dt(2026, 10, 1), last_seen=dt(2026, 10, 1)))
        s.commit()
        assert sagas.next_saga_id(s) == 18


def test_a_pair_of_stories_is_judged_once(db, monkeypatch):
    from app.analysis import sagas
    asked = []
    monkeypatch.setattr(sagas, 'saga_verdict', lambda a, b: asked.append((a, b)) or True)
    assert sagas.pair_verdict(9, 4, ['b1', 'b2', 'b3'], ['a1']) is True
    assert sagas.pair_verdict(4, 9, ['a1'], ['b1']) is True and len(asked) == 1
    with db() as s:
        row = s.get(t.SagaPair, (4, 9))
        assert row.judge == sagas.JUDGE_VERSION and json.loads(row.titles_a) == ['b1', 'b2']
        row.judge, row.hand, row.same = 1, True, False  # a person's verdict stands, whatever the judge
        s.commit()
    assert sagas.pair_verdict(4, 9, ['a1'], ['b1']) is False and len(asked) == 1
    monkeypatch.setattr(sagas, 'saga_verdict', lambda a, b: None)
    assert sagas.pair_verdict(1, 2, ['x'], ['y']) is None  # no answer: nothing remembered
    with db() as s:
        assert s.get(t.SagaPair, (1, 2)) is None


def test_label_times_are_kept_by_story(db):
    from app.analysis import stories
    stories.mark_labeled({7: dt(2026, 10, 9, 4, 5, 6, 789)})
    stories.mark_labeled({7: dt(2026, 10, 10, 1, 2, 3), 8: dt(2026, 10, 11)})
    assert stories.labeled_at() == {'7': '2026-10-10T01:02:03', '8': '2026-10-11T00:00:00'}


def test_name_aliases_merge_keep_apart_and_undo(db):
    from app.analysis import entities
    from scripts import validate
    entities.merge('Hochul', 'Kathy Hochul')
    entities.not_same('Georgia', 'Georgia Tech')
    entities.not_same('Georgia Tech', 'Georgia')  # once only
    book = entities.load_aliases()
    assert book['aliases']['hochul'] == 'Kathy Hochul' and book['aliases']['trump'] == 'Donald Trump'  # seeds too
    assert book['not_same'] == [['Georgia', 'Georgia Tech']]
    assert entities.chosen_aliases()['aliases'] == {'hochul': 'Kathy Hochul'}  # the seeds stay in the code
    before = validate.state(entities.ALIASES)
    entities.unmerge('Hochul')
    assert entities.canonical('Hochul', entities.load_aliases()['aliases']) == 'Hochul'
    validate.restore(entities.ALIASES, before)
    assert entities.canonical('Hochul', entities.load_aliases()['aliases']) == 'Kathy Hochul'
    assert validate.state(entities.ALIASES) == before


def test_story_extras_keep_every_item_newest_found_first(db, monkeypatch):
    from app.site import page_headlines as ph
    monkeypatch.setenv('MAUDLIN_STORY_EXTRAS', '1')

    def run(shows, curators, wording, at):
        monkeypatch.setattr(ph, 'dt', SimpleNamespace(utcnow=lambda: at))
        page = SimpleNamespace(story_of={0: 42}, context={'show_coverage': {0: shows}, 'investigations': [
            {'story': 0, 'source': 'ProPublica', 'title': 'Inside', 'url': 'p1', 'emoji': '🔎', 'color': '#000'}]})
        ph.HeadlinesPage.save_story_extras(page, [{'cluster': 0, 'curators': curators, 'wording': wording,
                                                   'quotes': [{'phrase': 'surges', 'count': 2}]},
                                                  {'cluster': 1}])  # a cluster saved as no story: nothing kept
    run([{'source': 'Up First', 'title': 'A', 'url': 'u1', 'color': '#b8b8c8', 'emoji': '🎙️'}], ['Drudge Report'],
        {'left': ['x']}, dt(2026, 10, 6, 18, 7, 30))
    run([{'source': 'CNN 5 Things', 'title': 'B', 'url': 'u2'}, {'source': 'Up First', 'title': 'A again', 'url': 'u1'}],
        ['Google News'], {}, dt(2026, 10, 7, 9, 0))
    [(sid, ex)] = ph.read_story_extras().items()
    assert sid == '42' and ex['updated'] == '2026-10-07T09:00'
    assert [(p['url'], p['title']) for p in ex['shows']] == [('u2', 'B'), ('u1', 'A again')]
    assert ex['curators'] == [{'source': 'Google News', 'seen': '2026-10-07T09:00'},
                              {'source': 'Drudge Report', 'seen': '2026-10-06T18:07'}]
    assert ex['quotes'] == [{'phrase': 'surges', 'count': 2}] and ex['factchecks'] == [] and ex['satire'] == []
    assert ex['investigations'][0]['url'] == 'p1'
    assert ex['wording'] == {'left': ['x']}  # a run with none keeps the last


def test_the_import_reads_every_file_and_moves_the_caches(db, tmp_path):
    from scripts.json_import import stories as imp
    data, cache = tmp_path / 'data', tmp_path / 'data' / 'cache'
    data.mkdir()
    files = {
        'story_merges.json': {'151': {'into': 136, 'label': 'Nobel', 'first_seen': '2026-10-06T17:10:28.895205',
                                      'headlines': [1, 2], 'at': '2026-10-07T13:08:14+00:00', 'why': 'by hand'}},
        'story_labeled_at.json': {'332': '2026-10-13T21:07:09'},
        'story_final_labels.json': {'436': {'at': '2026-10-14T15:06:54', 'from': 'Federal agents raid home'}},
        'sagas_ended.json': {'17': {'story': 136}, '2': {}, '39': {'saga': 30}},
        'saga_pairs.json': {'29|139': {'same': False, 'judge': 4, 'model': 'gemma4:26b', 'at': '2026-10-06T17:51:47+00:00',
                                       'a': ['x'], 'b': ['y']}},
        'story_extras.json': {'138': {'shows': [], 'factchecks': [{'source': 'Snopes', 'title': 'T', 'url': 'f1'}],
                                      'investigations': [], 'satire': [], 'quotes': [{'phrase': 'surges', 'count': 1}],
                                      'curators': [{'source': 'Drudge Report', 'seen': '2026-10-07T10:10'},
                                                   {'source': 'Google News', 'seen': '2026-10-06T20:10'}],
                                      'wording': {'right': [{'phrase': 'patient dies'}]}, 'updated': '2026-10-08T01:00'}},
        'entity_aliases.json': {'aliases': {'hochul': 'Kathy Hochul'},
                                'not_same': [['Tennessee', 'Georgia'], ['Georgia', 'Tennessee']]},
        'story_entities.json': {'s82': ['Spain']},
        'satire_links.json': {'b26b': '1'},
    }
    for name, content in files.items():
        (data / name).write_text(json.dumps(content))
    with db() as s:
        counts = imp.run(s, str(data), str(cache))
        s.commit()
    assert counts['story_merge'] == 1 and counts['story_split'] == 0 and counts['saga_ended'] == 3
    assert counts['story_extra_item'] == 4 and counts['entity_not_same'] == 1 and counts['caches_moved'] == 2
    assert (cache / 'story_entities.json').exists() and not (data / 'satire_links.json').exists()
    assert (data / 'story_merges.json').exists()  # sources are never deleted
    from app.analysis import entities, sagas, stories
    from app.site import page_headlines as ph
    assert stories.merges() == {151: 136} and stories.labeled_at() == {'332': '2026-10-13T21:07:09'}
    assert sagas.ended() == {17: {'story': 136}, 2: {}, 39: {'saga': 30}}
    with db() as s:
        assert s.get(t.StoryMerge, 151).at == dt(2026, 10, 7, 13, 8, 14)  # naive UTC
        assert s.get(t.SagaPair, (29, 139)).same is False
        assert s.get(t.StoryFinalLabel, 436).replaced == 'Federal agents raid home'
    ex = ph.read_story_extras()['138']
    assert [c['source'] for c in ex['curators']] == ['Drudge Report', 'Google News']
    assert ex['factchecks'] == [{'source': 'Snopes', 'title': 'T', 'url': 'f1'}]
    assert ex['wording'] == {'right': [{'phrase': 'patient dies'}]} and ex['updated'] == '2026-10-08T01:00'
    assert entities.chosen_aliases() == {'aliases': {'hochul': 'Kathy Hochul'}, 'not_same': [['Georgia', 'Tennessee']]}
    assert imp.run(db(), str(tmp_path / 'empty'), str(cache))['story_merge'] == 0  # missing files are fine


def test_a_split_is_remembered(db, monkeypatch):
    from app.analysis import stories
    from app.models import Headline, StoryHeadline
    now = dt(2026, 10, 15, 12)
    with db() as s:
        s.add(Story(id=1, label='Livestream planned', first_seen=now - td(days=3), last_seen=now))
        for i in range(6):
            s.add(Headline(id=i + 1, article_id=1, title=f'h{i}', first_accessed=now - td(hours=20 - 3 * i),
                           last_accessed=now))
            s.add(StoryHeadline(story_id=1, headline_id=i + 1, sentiment=0.0, deviation=0.0, last_seen=now))
        s.commit()
    monkeypatch.setattr(stories, 'same_event', lambda *a, **k: False)
    monkeypatch.setattr(stories, 'SPLIT_LEAST', 2)
    new = stories.split_development(1, now - td(hours=10), now)
    assert new is not None and stories.splits() == {1: new.id}
    with db() as s:
        row = s.get(t.StorySplit, 1)
        assert row.label == 'Livestream planned' and json.loads(row.headlines) == [6, 5]
