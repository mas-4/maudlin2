"""app/analysis/sagas.link_sagas: sagas kept across days, against an in-memory database and a fake embedding."""
from datetime import datetime as dt, timedelta as td, timezone

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.analysis.sagas as sg
from app.models import Agency, Article, Base, Headline, Saga, Story, StoryHeadline

# Titles about one running story (all mention Cornell) embed close together; the rest point elsewhere
TOPIC = {'Cornell': [1, 0, 0], 'rally': [0, 1, 0]}


def fake_embed(titles):
    out = []
    for t in titles:
        v = next((v for k, v in TOPIC.items() if k in t), [0, 0, 1])
        out.append(v)
    return np.array(out, float) + 0.01


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(sg, 'Session', session)
    monkeypatch.setattr(sg, 'embed', fake_embed)
    monkeypatch.setattr(sg, 'name', lambda stories, clusters: 'Cornell case')
    monkeypatch.setattr(sg, 'same_saga', lambda a, b: True)  # the language model agrees (tests never call it)
    return session


def saved_story(session, titles, hours_ago, saga_id=None):
    now = dt.now(timezone.utc).replace(tzinfo=None) - td(hours=hours_ago)
    with session() as s:
        agency = s.query(Agency).first() or Agency(name='AP', url='x', _bias=0, _credibility=0, _country=0)
        story = Story(label=titles[0], first_seen=now, last_seen=now, saga_id=saga_id)
        s.add_all([agency, story])
        s.flush()
        for n, t in enumerate(titles):
            article = Article(url=f'{story.id}-{n}', agency=agency)
            h = Headline(title=t, article=article)
            s.add_all([article, h])
            s.flush()
            s.add(StoryHeadline(story_id=story.id, headline_id=h.id, sentiment=0, deviation=0, last_seen=now))
        s.commit()
        return story.id


def today(clusters: dict[int, list[str]], filler=400):  # a day has thousands of headlines
    rows = [{'title': t, 'agency': f'Outlet {i}', 'cluster': k} for k, ts in clusters.items() for i, t in enumerate(ts)]
    rows += [{'title': f'Unrelated news item number {i}', 'agency': 'X', 'cluster': -1} for i in range(filler)]
    headlines = pd.DataFrame(rows)
    return headlines, headlines[headlines['cluster'] != -1]


def test_sentence_case_capitals_are_names_title_case_ignored():
    titles = ['Students at Cornell protest the ruling', 'Prosecutor takes over the Cornell case',
              'Trump Holds Rally In Alabama', 'Crowds gather for the rally tonight']
    names = sg.proper_nouns(titles)
    assert 'cornell' in names and 'rally' not in names and 'alabama' not in names


def test_yesterdays_parts_stay_in_todays_saga(db):
    old1 = saved_story(db, ['Cornell student alleges assault', 'Cornell accuser speaks out'], 30)
    old2 = saved_story(db, ['Governor appoints prosecutor in Cornell case', 'Prosecutor named in Cornell case'], 26)
    headlines, stories = today({0: ['Attorney general takes over Cornell investigation',
                                    'New details in the Cornell investigation']})
    sagas = sg.link_sagas(headlines, stories, {0: saved_story(db, ['Attorney general takes over Cornell case'], 1)})
    [saga] = sagas.values()
    assert saga['size'] == 3 and saga['clusters'] == [0]
    assert [p['cluster'] for p in saga['parts_all']][:2] == [None, None]  # earlier parts, off the front pages
    with db() as s:
        assert {st.id for st in s.query(Story).filter(Story.saga_id == saga['id'])} >= {old1, old2}


def test_saved_saga_never_loses_a_part_and_keeps_its_id(db):
    with db() as s:
        saga = Saga(name='Cornell case', named_with=2, first_seen=dt.now(timezone.utc).replace(tzinfo=None), last_seen=dt.now(timezone.utc).replace(tzinfo=None))
        s.add(saga)
        s.commit()
        saga_id = saga.id
    # an old part that no longer resembles anything today still belongs
    saved_story(db, ['A quiet procedural update'], 40, saga_id=saga_id)
    current = saved_story(db, ['Cornell hearing set'], 1, saga_id=saga_id)
    headlines, stories = today({0: ['Cornell hearing set for Monday', 'Judge sets Cornell hearing']})
    [saga] = sg.link_sagas(headlines, stories, {0: current}).values()
    assert saga['id'] == saga_id and saga['size'] == 2


def test_common_noun_alone_does_not_link(db):
    saved_story(db, ['Trump Holds Rally In Alabama', 'crowds gather for the rally in Mobile'], 20)
    headlines, stories = today({0: ['factory lays off workers before the rally', 'layoffs ahead of the rally']})
    assert sg.link_sagas(headlines, stories, {0: saved_story(db, ['factory layoffs'], 1)}) == {}


def test_only_active_sagas_returned_and_ids_negative(db):
    saved_story(db, ['Cornell student alleges assault', 'Cornell accuser speaks out'], 30)
    headlines, stories = today({0: ['Investigators widen the Cornell inquiry', 'Prosecutors grow the Cornell probe'],
                                1: ['Unrelated weather story', 'Storm hits coast']})
    sagas = sg.link_sagas(headlines, stories, {0: saved_story(db, ['Cornell probe'], 1),
                                               1: saved_story(db, ['Storm'], 1)})
    assert all(k < 0 for k in sagas) and len(sagas) == 1


def test_language_model_veto_blocks_a_link(db, monkeypatch):
    asked = []
    monkeypatch.setattr(sg, 'same_saga', lambda a, b: asked.append((a, b)) or False)
    saved_story(db, ['Cornell student alleges assault', 'Cornell accuser speaks out'], 30)
    headlines, stories = today({0: ['Attorney general takes over Cornell investigation',
                                    'New details in the Cornell investigation']})
    assert sg.link_sagas(headlines, stories, {0: saved_story(db, ['Attorney general takes over Cornell case'], 1)}) == {}
    assert len(asked) == 1  # asked once per pair, not again in the same run


def test_same_saga_caches_and_never_links_without_an_answer(monkeypatch, tmp_path):
    monkeypatch.setattr(sg, 'JUDGMENTS', str(tmp_path / 'judgments.json'))
    monkeypatch.setattr(sg.llm, 'complete_json', lambda *a, **k: None)
    assert sg.same_saga(['Supreme Court takes detention case'], ['Supreme Court takes climate case']) is False
    calls = []
    monkeypatch.setattr(sg.llm, 'complete_json',
                        lambda *a, **k: calls.append(a) or {'reason': 'different cases', 'same_story': False})
    monkeypatch.setattr(sg.llm, 'model', lambda: 'fake')
    for _ in range(2):  # either order, asked once
        assert sg.same_saga(['Supreme Court takes climate case'], ['Supreme Court takes detention case']) is False
        assert sg.same_saga(['Supreme Court takes detention case'], ['Supreme Court takes climate case']) is False
    assert len(calls) == 1
