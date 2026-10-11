"""app/analysis/stories.sync_stories against an in-memory database (never data/data.db)."""
from datetime import datetime as dt

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.analysis.stories as stories
from app.models import Base, Story, StoryHeadline


@pytest.fixture
def db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(stories, 'Session', session)
    return session


def frame(clusters: dict[int, list[int]]) -> pd.DataFrame:
    rows = [{'cluster': c, 'headline_id': h, 'afinn': 0.0, 'vader_compound': 0.0, 'event_score': 0.0}
            for c, ids in clusters.items() for h in ids]
    return pd.DataFrame(rows)


def seed(session, label, headline_ids):
    now = dt(2026, 10, 3)
    with session() as s:
        story = Story(label=label, first_seen=now, last_seen=now)
        s.add(story)
        s.flush()
        for h in headline_ids:
            s.add(StoryHeadline(story_id=story.id, headline_id=h, sentiment=0.0, deviation=0.0, last_seen=now))
        s.commit()
        return story.id


def test_new_cluster_makes_a_new_story(db):
    out = stories.sync_stories(frame({0: [1, 2, 3]}))
    assert out[0].id is not None and out[0].label is None


def test_cluster_continues_the_story_holding_most_of_its_headlines(db):
    old = seed(db, 'G7 agrees to release oil', [1, 2, 3, 4])
    out = stories.sync_stories(frame({0: [1, 2, 3, 9]}))
    assert out[0].id == old and out[0].label == 'G7 agrees to release oil'


def test_split_story_gives_the_smaller_part_its_own_story(db):
    # #147: one story's coverage split into two clusters this hour; both used to map to the same story and show
    # as two cards with the same title
    old = seed(db, 'G7 agrees to release oil', [1, 2, 3, 4, 5, 6])
    out = stories.sync_stories(frame({0: [5, 6, 20], 1: [1, 2, 3, 4, 10, 11]}))
    assert out[1].id == old  # the bigger part keeps the story and its title
    assert out[0].id != old and out[0].label is None  # the smaller part is new, to be titled on its own
    with db() as s:
        moved = {sh.headline_id: sh.story_id for sh in s.query(StoryHeadline)}
    assert moved[5] == moved[6] == moved[20] == out[0].id
    assert moved[1] == moved[10] == old


def test_smaller_part_falls_back_to_its_next_best_story(db):
    first = seed(db, 'Main story', [1, 2, 3, 4])
    second = seed(db, 'Older follow-up', [7, 8])
    out = stories.sync_stories(frame({0: [1, 2, 3, 4, 30], 1: [4, 7, 8]}))
    assert out[0].id == first
    assert out[1].id == second


def test_a_story_whose_news_moved_on_is_labeled_again_from_its_newest_headlines(db, monkeypatch, tmp_path):
    """Oct 11: an Oct 2 label stood over nine days of a story's later news (its outlet count never doubled)"""
    from datetime import timedelta as td
    monkeypatch.setattr(stories, 'LABELED_AT', str(tmp_path / 'labeled_at.json'))
    monkeypatch.setattr(stories.llm, 'backend', lambda: 'ollama')
    shown = []

    def ask(prompt, schema, **k):
        shown.append(prompt)
        return {'title': 'Pike discharged from hospital'}
    monkeypatch.setattr(stories.llm, 'complete_json', ask)
    now = dt.now(stories.pytz.UTC).replace(tzinfo=None)
    with db() as s:
        old = Story(label='Inmate survives execution attempt', labeled_with=3, first_seen=now - td(days=9),
                    last_seen=now)
        quiet = Story(label='A quiet story', labeled_with=3, first_seen=now - td(days=3), last_seen=now)
        fresh = Story(label='A new story', labeled_with=3, first_seen=now - td(hours=2), last_seen=now)
        s.add_all([old, quiet, fresh])
        s.commit()
        ids = old.id, quiet.id, fresh.id
        found = {k: s.get(Story, i) for k, i in enumerate(ids)}
    # As the front page hands it over: first_seen the time in Eastern, first_accessed already display text
    rows = [(0, 'a', 'Inmate survives execution', td(days=9)), (0, 'b', 'Pike leaves hospital', td(hours=1)),
            (1, 'a', 'Nothing new', td(days=3)), (2, 'a', 'Just in', td(hours=1))]
    df = pd.DataFrame([{'cluster': c, 'agency': a, 'title': t,
                        'first_seen': pd.Timestamp(now - ago, tz='UTC').tz_convert('US/Eastern')} for c, a, t, ago in rows])
    df['first_accessed'] = ['Oct 9 4:04 PM', 'Oct 11 9:03 AM', 'Oct 9 4:04 PM', 'Oct 11 9:03 AM']  # Oct 9 > Oct 11 as text
    labels = stories.label_stories(df, found)
    assert labels == {0: 'Pike discharged from hospital', 1: 'A quiet story', 2: 'A new story'}
    assert len(shown) == 1 and shown[0].index('Pike leaves hospital') < shown[0].index('Inmate survives execution')
    stories.label_stories(df, found)
    assert len(shown) == 1  # labeled now: not again until it's old and has news
