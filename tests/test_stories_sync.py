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


def live(session, label, headline_ids, first):
    """A story on the front pages until a moment ago, begun at `first`"""
    import pytz
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    with session() as s:
        story = Story(label=label, first_seen=first, last_seen=now)
        s.add(story)
        s.flush()
        for h in headline_ids:
            s.add(StoryHeadline(story_id=story.id, headline_id=h, sentiment=0.0, deviation=0.0, last_seen=now))
        s.commit()
        return story.id


def test_a_story_split_and_joined_again_carries_on_as_the_older(db, monkeypatch, tmp_path):
    """Oct 13: Christa Pike split at 1 AM, the halves joined at 8 and the young half carried on; now the older does,
    with the younger folded in, when the model says they tell the same event"""
    monkeypatch.setattr(stories, 'MERGES', str(tmp_path / 'merges.json'))
    asked = []
    monkeypatch.setattr(stories, 'rejoined', lambda s, a, b, lesser, size, now: asked.append((lesser, size)) or
                        tuple(sorted((a, b), key=lambda x: x.first_seen)))
    old = live(db, 'Christa Pike discharged from hospital', [1, 2, 3], dt(2026, 10, 2))
    young = live(db, 'Christa Pike discharged after failed execution', [4, 5, 6, 7, 8], dt(2026, 10, 13))
    out = stories.sync_stories(frame({0: [2, 3, 4, 5, 6, 7]}))
    assert out[0].id == old and asked == [(2, 6)]
    with db() as s:
        assert s.get(Story, young) is None
        assert {sh.story_id for sh in s.query(StoryHeadline)} == {old}  # the younger's other headlines came too
    assert stories.merges() == {young: old}


def test_two_live_stories_the_model_calls_different_stay_apart(db, monkeypatch, tmp_path):
    monkeypatch.setattr(stories, 'MERGES', str(tmp_path / 'merges.json'))
    monkeypatch.setattr(stories, 'same_event', lambda *a, **kw: False)
    a = live(db, 'Game 1', [1, 2, 3, 4], dt(2026, 10, 2))
    b = live(db, 'Game 2', [5, 6, 7], dt(2026, 10, 3))
    out = stories.sync_stories(frame({0: [1, 2, 3, 4, 5, 6, 7]}))
    assert out[0].id == a
    with db() as s:
        assert s.get(Story, b) is not None


def test_a_story_that_left_the_front_pages_is_titled_once_more_from_its_last_headlines(db, monkeypatch, tmp_path):
    """Oct 14, saga 48: a part titled for the Maine debate held ten Georgia headlines once the Maine ones had gone"""
    import pytz
    from datetime import timedelta as td
    from app.models import Headline
    monkeypatch.setattr(stories, 'FINALS', str(tmp_path / 'finals.json'))
    monkeypatch.setattr(stories, 'LABELED_AT', str(tmp_path / 'labeled_at.json'))
    monkeypatch.setattr(stories.llm, 'backend', lambda: 'ollama')
    asked = []
    monkeypatch.setattr(stories.llm, 'complete_json', lambda prompt, *a, **kw: asked.append(prompt) or
                        {'title': 'Ossoff and Collins clash in Georgia Senate debate'})
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    with db() as s:
        gone = Story(label='Senators Collins and Jackson debate in Maine', first_seen=now - td(days=4), last_seen=now - td(days=3))
        live = Story(label='On now', first_seen=now, last_seen=now)
        s.add_all([gone, live])
        s.flush()
        for i, t in enumerate(['Ossoff, Collins clash in Georgia Senate debate', 'Five takeaways from the Georgia debate']):
            s.add(Headline(id=i + 1, article_id=1, title=t, first_accessed=now - td(days=3), last_accessed=now - td(days=3)))
            s.add(StoryHeadline(story_id=gone.id, headline_id=i + 1, sentiment=0.0, deviation=0.0, last_seen=now))
        s.commit()
        gone_id = gone.id
    assert stories.label_ended(now) == {gone_id: 'Ossoff and Collins clash in Georgia Senate debate'}
    assert 'Georgia debate' in asked[0] and len(asked) == 1  # the live story isn't touched
    assert stories.label_ended(now) == {} and len(asked) == 1  # once only


# ---------- a live story split where its news moved on to a new development (switched off: SPLIT_DEVELOPMENTS) ----------

@pytest.fixture(autouse=True)
def no_real_splits(monkeypatch, tmp_path):
    """Never the data folder's record of splits: its story ids would be read against the test's"""
    monkeypatch.setattr(stories, 'SPLITS', str(tmp_path / 'splits.json'))


def running(session, tmp_path, monkeypatch, saga=True):
    """Fort Hood, Oct 15: a story titled 13 hours ago for the livestream plan, four headlines since on its cancellation.
    Returns (story id, the headlines' first sightings, the run's frame, its Story objects by cluster)"""
    import pytz
    from datetime import timedelta as td
    from app.models import Headline, Saga
    monkeypatch.setattr(stories, 'LABELED_AT', str(tmp_path / 'labeled_at.json'))
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    titles = ['Pentagon will livestream Fort Hood execution', 'Hegseth plans livestreamed execution',
              'Backlash over livestream plan', 'Vance would not watch livestream',
              'Trump cancels livestream of execution', "Trump says Pentagon won't livestream execution",
              'Livestream called off after backlash', 'Trump scraps execution livestream']
    ago = [td(days=3), td(days=2), td(hours=20), td(hours=14), td(hours=6), td(hours=3), td(hours=2), td(hours=1)]
    with session() as s:
        saga_id = None
        if saga:
            sg = Saga(name='Fort Hood shooter execution', first_seen=now - td(days=9), last_seen=now)
            s.add(sg)
            s.flush()
            saga_id = sg.id
        story = Story(label='Pentagon to livestream Fort Hood execution', labeled_with=4, first_seen=now - td(days=3),
                      last_seen=now, saga_id=saga_id)
        s.add(story)
        s.flush()
        for i, (t, a) in enumerate(zip(titles, ago), 1):
            s.add(Headline(id=i, article_id=i, title=t, first_accessed=now - a, last_accessed=now))
            s.add(StoryHeadline(story_id=story.id, headline_id=i, sentiment=0.0, deviation=0.0, last_seen=now))
        s.commit()
        sid = story.id
        found = {0: s.get(Story, sid)}
    stories.write_json(stories.LABELED_AT, {str(sid): (now - td(hours=13)).isoformat(timespec='seconds')})
    rows = [(i, t, a) for i, (t, a) in enumerate(zip(titles, ago), 1) if a < td(hours=15)]  # on the front pages now
    df = pd.DataFrame([{'cluster': 0, 'headline_id': i, 'agency': f'outlet {i}', 'title': t,
                        'first_seen': pd.Timestamp(now - a, tz='UTC').tz_convert('US/Eastern')} for i, t, a in rows])
    return sid, {i: now - a for i, a in enumerate(ago, 1)}, df, found


def fake_model(monkeypatch, same: bool | None, title='Trump cancels livestream of Fort Hood execution'):
    asked, shown = [], []
    monkeypatch.setattr(stories.llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(stories, 'same_event', lambda a, b, prompt=None: asked.append((a, b, prompt)) or same)
    monkeypatch.setattr(stories.llm, 'complete_json', lambda prompt, *a, **kw: shown.append(prompt) or {'title': title})
    return asked, shown


def test_a_story_whose_newest_headlines_are_a_new_development_splits(db, monkeypatch, tmp_path):
    """Oct 15: the cancellation of the Fort Hood livestream became the tenth day of one story, not a part of its own"""
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    sid, first, df, found = running(db, tmp_path, monkeypatch)
    asked, shown = fake_model(monkeypatch, same=False)
    labels = stories.label_stories(df, found)
    assert len(asked) == 1 and asked[0][2] == stories.SPLIT_PROMPT
    assert asked[0][0][0] == 'Vance would not watch livestream'  # the earlier side, newest first
    assert asked[0][1][0] == 'Trump scraps execution livestream'
    new = found[0]
    assert new.id != sid and labels == {0: 'Trump cancels livestream of Fort Hood execution'}
    assert 'Vance' not in shown[0] and 'Trump scraps' in shown[0]  # titled from the new development alone
    with db() as s:
        old, made = s.get(Story, sid), s.get(Story, new.id)
        held = {sh.headline_id: sh.story_id for sh in s.query(StoryHeadline)}
        assert old.label == 'Pentagon to livestream Fort Hood execution'  # kept, for label_ended to write once more
        assert old.last_seen == first[4]  # ended with its last kept headline
        assert made.saga_id == old.saga_id is not None and made.label == labels[0]
        assert made.first_seen == first[5]
    assert held == {1: sid, 2: sid, 3: sid, 4: sid, 5: new.id, 6: new.id, 7: new.id, 8: new.id}
    assert stories.splits() == {sid: new.id}


def test_a_split_of_a_story_in_no_saga_makes_one_for_the_two(db, monkeypatch, tmp_path):
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    sid, _, df, found = running(db, tmp_path, monkeypatch, saga=False)
    fake_model(monkeypatch, same=False)
    stories.label_stories(df, found)
    with db() as s:
        assert s.get(Story, sid).saga_id is not None
        assert s.get(Story, sid).saga_id == s.get(Story, found[0].id).saga_id


@pytest.mark.parametrize('same', [True, None])
def test_the_same_news_told_again_or_no_answer_only_retitles(db, monkeypatch, tmp_path, same):
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    sid, _, df, found = running(db, tmp_path, monkeypatch)
    asked, _ = fake_model(monkeypatch, same=same)
    labels = stories.label_stories(df, found)
    assert len(asked) == 1 and found[0].id == sid and labels[0] == 'Trump cancels livestream of Fort Hood execution'
    with db() as s:
        assert {sh.story_id for sh in s.query(StoryHeadline)} == {sid}
    assert stories.splits() == {}


def test_switched_off_nothing_is_asked(db, monkeypatch, tmp_path):
    assert stories.SPLIT_DEVELOPMENTS is False  # on only after Sinbad's result and the person's verdicts
    assert 'one running news story' in stories.SPLIT_PROMPT and 'Newest:\n{b}' in stories.SPLIT_PROMPT  # reworded
    sid, _, df, found = running(db, tmp_path, monkeypatch)
    asked, _ = fake_model(monkeypatch, same=False)
    stories.label_stories(df, found)
    assert asked == [] and found[0].id == sid


def test_the_next_run_goes_on_with_the_new_development_not_the_old_story(db, monkeypatch, tmp_path):
    """The old development's headlines still on the front pages outnumber the new ones: the cluster still goes on as
    the new story (the old one is never continued nor rejoined), and those headlines stay with the old story"""
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    monkeypatch.setattr(stories, 'MERGES', str(tmp_path / 'merges.json'))
    sid, _, df, found = running(db, tmp_path, monkeypatch)
    fake_model(monkeypatch, same=False)
    stories.label_stories(df, found)
    new = found[0].id
    monkeypatch.setattr(stories, 'rejoined', lambda *a: pytest.fail('a split is never put to the rejoin rule'))
    out = stories.sync_stories(frame({0: [1, 2, 3, 4, 5, 9]}))
    assert out[0].id == new
    with db() as s:
        held = {sh.headline_id: sh.story_id for sh in s.query(StoryHeadline)}
    assert held[1] == held[4] == sid and held[5] == held[9] == new


def test_a_story_ended_by_a_split_is_not_a_return(db, monkeypatch, tmp_path):
    import pytz
    from datetime import timedelta as td
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    sid, _, df, found = running(db, tmp_path, monkeypatch)
    fake_model(monkeypatch, same=False)
    stories.label_stories(df, found)
    monkeypatch.setattr(stories, 'same_event', lambda *a, **kw: True)  # told again: of the two, the new one returns
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    with db() as s:
        back = stories.returning(s, ['Pentagon livestream execution plan', 'Hegseth livestream execution plan'],
                                 set(), now + td(hours=3))
        assert back is not None and back.id == found[0].id != sid


def test_a_story_due_when_the_runs_questions_are_spent_waits_for_the_next_run(db, monkeypatch, tmp_path):
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    monkeypatch.setattr(stories, 'MAX_SPLIT_CHECKS', 0)
    sid, _, df, found = running(db, tmp_path, monkeypatch)
    asked, shown = fake_model(monkeypatch, same=False)
    labels = stories.label_stories(df, found)
    assert asked == shown == [] and labels == {0: 'Pentagon to livestream Fort Hood execution'}


def test_a_story_whose_coverage_doubled_is_asked_too(db, monkeypatch, tmp_path):
    """Oct 15: the cancellation took Fort Hood from 6 outlets to 35 in an hour, a coverage retitle, not a stale one"""
    import pytz
    from datetime import timedelta as td
    monkeypatch.setattr(stories, 'SPLIT_DEVELOPMENTS', True)
    sid, _, df, found = running(db, tmp_path, monkeypatch)
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    stories.write_json(stories.LABELED_AT, {str(sid): (now - td(hours=7)).isoformat(timespec='seconds')})
    found[0].labeled_with = 2  # 4 outlets now
    asked, _ = fake_model(monkeypatch, same=False)
    stories.label_stories(df, found)
    assert len(asked) == 1 and found[0].id != sid


# ---- one story's coverage split by an hour's clustering, the smaller part sharing no headline with the story

def told(clusters: dict[int, list[tuple[int, str, str]]], roots: dict[int, int] | None = None) -> pd.DataFrame:
    """A run's clusters with their headlines' titles and outlets: {cluster: [(headline id, outlet, title)]}"""
    rows = [{'cluster': c, 'headline_id': h, 'agency': a, 'title': t, 'afinn': 0.0, 'vader_compound': 0.0,
             'event_score': 0.0, **({'seam_root': roots[c]} if roots else {})}
            for c, hs in clusters.items() for h, a, t in hs]
    return pd.DataFrame(rows)


RFK_THEN = 'RFK Jr faces backlash for anti-Arab remarks'
RFK_NOW = 'RFK Jr. faces backlash over anti-Arab remarks'


def test_a_story_split_by_this_hours_clustering_carries_on_as_one(db, monkeypatch):
    """Oct 28, saga 99 (the person: "this saga has 2 stories that are the same"): at noon the clustering split the
    RFK coverage in two; the part with new wording matched nothing and, the story being live, was no return either,
    so it started a story of its own that carried on while the first ran out"""
    asked = []
    monkeypatch.setattr(stories, 'same_event', lambda a, b, prompt=None: asked.append(prompt) or True)
    old = seed(db, RFK_THEN, [1, 2, 3])
    df = told({0: [(1, 'CNN', RFK_THEN), (2, 'NBC', RFK_THEN + ' in interview'), (3, 'AP', RFK_THEN + ', aides say')],
               1: [(10, 'Fox', RFK_NOW), (11, 'Newsmax', RFK_NOW + ' on podcast')]})
    out = stories.sync_stories(df)
    assert out[0].id == out[1].id == old and asked == [stories.REJOIN_PROMPT]
    with db() as s:
        assert {sh.headline_id: sh.story_id for sh in s.query(StoryHeadline)} == {1: old, 2: old, 3: old, 10: old, 11: old}
    folded, kept = stories.fold_twins(df, out)
    assert set(kept) == {0} and set(folded['cluster']) == {0} and len(folded) == 5  # one card


def test_a_split_part_the_model_calls_a_different_event_keeps_its_own_story(db, monkeypatch):
    """#147, Oct 3: the G7 release and 'Trump rules out a diesel export ban' were two events, rightly two stories"""
    monkeypatch.setattr(stories, 'same_event', lambda a, b, prompt=None: False)
    old = seed(db, 'G7 agrees to release diesel and oil', [1, 2, 3])
    df = told({0: [(1, 'CNN', 'G7 agrees to release diesel and oil reserves'), (2, 'AP', 'G7 to release diesel and oil'),
                   (3, 'NBC', 'G7 diesel and oil release agreed')],
               1: [(10, 'Fox', 'Trump rules out diesel export ban'), (11, 'The Hill', 'No diesel export ban, Trump says')]})
    out = stories.sync_stories(df)
    assert out[0].id == old and out[1].id != old


def test_the_sides_of_this_runs_seam_cut_are_never_joined_again(db, monkeypatch):
    """The seam cut parted them because the model, asked both ways, called them two events (clustering.split_seams)"""
    asked = []
    monkeypatch.setattr(stories, 'same_event', lambda a, b, prompt=None: asked.append(1) or True)
    old = seed(db, RFK_THEN, [1, 2, 3])
    df = told({0: [(1, 'CNN', RFK_THEN), (2, 'NBC', RFK_THEN + ' in interview'), (3, 'AP', RFK_THEN + ', aides say')],
               1: [(10, 'Fox', RFK_NOW), (11, 'Newsmax', RFK_NOW + ' on podcast')]}, roots={0: 7, 1: 7})
    out = stories.sync_stories(df)
    assert out[0].id == old and out[1].id != old and not asked


def test_folding_twins_keeps_one_headline_an_outlet(db):
    a, b = Story(id=5), Story(id=6)
    df = told({0: [(1, 'CNN', 'x one'), (2, 'AP', 'x two')], 1: [(3, 'CNN', 'x three'), (4, 'Fox', 'x four')],
               2: [(9, 'AP', 'other')]})
    folded, kept = stories.fold_twins(df, {0: a, 1: a, 2: b})
    assert set(kept) == {0, 2}
    assert sorted(folded[folded['cluster'] == 0]['headline_id']) == [1, 2, 4]  # CNN's from the first part
