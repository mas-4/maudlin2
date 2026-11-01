"""A story back on the front pages under new headlines continues the old story (app/analysis/stories.py): the
candidates by shared frequent words, the model's same-event verdict cached, merges followed to the end."""

from app.analysis import llm, stories


def test_frequent_words_skip_stop_words_and_rare_ones():
    titles = ['Francis Halzen wins Nobel Prize in physics', 'Halzen wins physics Nobel for neutrinos',
              'Nobel physics prize goes to neutrino hunter']
    words = stories.frequent_words(titles)
    assert {'halzen', 'nobel', 'physics', 'wins'} <= words and 'with' not in words
    assert 'hunter' not in stories.frequent_words(titles, share=0.5)


def test_same_event_asks_once_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(stories, 'RETURNS', str(tmp_path / 'returns.json'))
    calls = []

    def fake(prompt, schema, max_tokens=0, model=None):
        calls.append(prompt)
        return {'reason': 'the same award', 'verdict': 'the same event'}
    monkeypatch.setattr(llm, 'complete_json', fake)
    a, b = ['Halzen wins physics Nobel'], ['Belgian-American scientist wins Nobel Prize in physics']
    assert stories.same_event(a, b) is True and stories.same_event(a, b) is True
    assert len(calls) == 1 and 'Go by what most headlines' in calls[0]
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: None)
    assert stories.same_event(['x'], ['y']) is None  # no answer: nothing remembered


def test_merges_follow_chains(monkeypatch):
    from datetime import datetime as dt
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool
    import app.models as models
    from app.tables.stories import StoryMerge
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    monkeypatch.setattr(models, 'Session', sessionmaker(bind=engine))
    with models.Session() as s:
        s.add_all(StoryMerge(gone=g, into=i, at=dt(2026, 10, 7)) for g, i in ((151, 136), (136, 120), (7, 9)))
        s.commit()
    assert stories.merges() == {151: 120, 136: 120, 7: 9}
