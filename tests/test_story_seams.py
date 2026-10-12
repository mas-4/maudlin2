import numpy as np

from app.analysis import clustering


def test_a_story_of_two_events_is_cut_at_its_seam():
    a = [f'nobel peace prize awarded to activist {i}' for i in range(7)]
    b = [f'musk sues openai over charity {i}' for i in range(7)]
    texts = a + b
    outlets = [f'outlet{i}' for i in range(14)]  # Atropos cut only stories of 12+ outlets
    out, made = clustering.split_seams([set(range(14))], texts, outlets, min_outlets=6)
    assert sorted(len(c) for c in out) == [7, 7] and made and made[0]['ncut'] < clustering.SEAM
    assert {frozenset(c) for c in out} == {frozenset(range(7)), frozenset(range(7, 14))}


def test_one_event_told_alike_stays_whole():
    texts = [f'pope leo to undergo lung surgery for nodule removal {w}' for w in
             ['today', 'monday', 'vatican says', 'doctors', 'report', 'update', 'news', 'rome', 'friday', 'week', 'live', 'now']]
    outlets = [f'outlet{i}' for i in range(12)]
    out, made = clustering.split_seams([set(range(12))], texts, outlets, min_outlets=6)
    assert len(out) == 1 and not made


def test_small_stories_are_never_cut():
    out, made = clustering.split_seams([{0, 1, 2}], ['a b', 'c d', 'e f'], ['x', 'y', 'z'], min_outlets=6)
    assert out == [{0, 1, 2}] and not made
    assert np.isclose(clustering.SEAM, 0.6)


def test_a_cut_the_judge_calls_one_event_is_not_made():
    a = [f'nobel peace prize awarded to activist {i}' for i in range(7)]
    b = [f'musk sues openai over charity {i}' for i in range(7)]
    outlets = [f'outlet{i}' for i in range(14)]
    seen = []
    out, made = clustering.split_seams([set(range(14))], a + b, outlets, 6, confirm=lambda x, y: seen.append((x, y)) or False)
    assert len(out) == 1 and not made and seen and len(seen[0][0]) <= clustering.SEAM_SHOWN


def test_two_events_needs_both_wordings(monkeypatch):
    from app.analysis import llm
    answers = iter([{'one_event': False, 'reason': 'two'}, {'one_event': True, 'reason': 'one card'}])
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: next(answers))
    cache = {}
    assert clustering.two_events(['a'], ['b'], cache) is False  # the wordings disagree: kept whole
    assert clustering.two_events(['a'], ['b'], cache) is False  # and cached, not asked again
