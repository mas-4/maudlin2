"""Sagas: grouping stories into running stories. The embedding model is replaced by fixed vectors per headline, and
the llm by a fake, so these run in milliseconds and offline."""
from collections import Counter

import numpy as np
import pandas as pd
import pytest

from app.analysis import llm, sagas
from app.analysis.sagas import find_sagas, words


@pytest.mark.parametrize('title, expected', [
    ('Cornell case grows', {'cornell', 'case', 'grows'}),
    ('Trump’s war on the Fed', {'trump'}),  # the curly apostrophe ends the word; short words dropped
    ("Trump's 'human printer'", {"trump's", 'human', 'printer'}),
    ('Kyiv-Moscow talks stall', {'kyiv', 'moscow', 'talks', 'stall'}),  # hyphens split words
    ('UN to vote on it', {'vote'}),  # three letters or fewer don't count
    ('2024 votes', {'votes'}),
    ('', set()),
])
def test_words(title, expected):
    assert words(title) == expected


def test_words_lowercases_and_dedupes():
    assert words('Cornell CORNELL cornell') == {'cornell'}


def unit(*pairs, dim=8):
    v = np.zeros(dim)
    for i, x in pairs:
        v[i] = x
    return v


# Fixed vectors: two Cornell stories close together, a Ukraine story that's close to them in embedding space but
# shares no distinctive word, and an unrelated hurricane story far away
VECTORS = {
    'Cornell fraternity case grows': unit((0, 1), (1, .2)),
    'Cornell fraternity faces charges': unit((0, 1), (1, .25)),
    'Hochul hands Cornell case to attorney general': unit((0, 1), (2, .3)),
    'Attorney general takes Cornell probe': unit((0, 1), (2, .35)),
    'Ukraine peace talks resume': unit((0, 1), (3, .3)),
    'Ukraine envoys meet again': unit((0, 1), (3, .35)),
    'Hurricane Milton nears Florida': unit((4, 1)),
    'Florida braces for Milton': unit((4, 1), (5, .1)),
    'Cornell students protest ruling': unit((0, 1), (1, .1)),  # unclustered but belongs
    'Students protest tuition costs': unit((6, 1)),  # unclustered and unrelated
}


@pytest.fixture
def fake_embed(monkeypatch):
    calls = []

    def embed(texts):
        calls.append(list(texts))
        return np.array([VECTORS[t] for t in texts])

    monkeypatch.setattr(sagas, 'embed', embed)
    # With only ten headlines every word is "common" at the real 4% cap, so loosen it for the toy day
    monkeypatch.setattr(sagas, 'NAME_MAX_SHARE', 0.5)
    monkeypatch.setattr(sagas, '_names', {})
    return calls


@pytest.fixture
def fake_llm(monkeypatch):
    prompts = []

    def complete_json(prompt, schema, max_tokens=1024):
        prompts.append(prompt)
        return {'name': '"Cornell fraternity case"'}

    monkeypatch.setattr(llm, 'complete_json', complete_json)
    return prompts


ROWS = [  # title, agency, cluster
    ('Cornell fraternity case grows', 'NYT', 0),
    ('Cornell fraternity faces charges', 'Fox', 0),
    ('Hochul hands Cornell case to attorney general', 'CNN', 1),
    ('Attorney general takes Cornell probe', 'NYT', 1),
    ('Ukraine peace talks resume', 'BBC', 2),
    ('Ukraine envoys meet again', 'Reuters', 2),
    ('Hurricane Milton nears Florida', 'AP', 3),
    ('Florida braces for Milton', 'NPR', 3),
    ('Cornell students protest ruling', 'Daily Beast', -1),
    ('Students protest tuition costs', 'Axios', -1),
]


def frames(rows=ROWS):
    headlines = pd.DataFrame(rows, columns=['title', 'agency', 'cluster'])
    return headlines, headlines[headlines['cluster'] >= 0].copy()


def test_no_stories_no_sagas(fake_embed, fake_llm):
    headlines, stories = frames()
    assert find_sagas(headlines, stories.iloc[0:0]) == {}
    assert fake_embed == []  # returns before embedding anything


def test_related_stories_form_a_saga(fake_embed, fake_llm):
    result = find_sagas(*frames())
    assert list(result) == [0]
    saga = result[0]
    assert sorted(saga['clusters']) == [0, 1]
    assert 'cornell' in saga['words']
    assert saga['words'] == sorted(saga['words'])
    assert saga['name'] == 'Cornell fraternity case'  # quotes stripped


def test_saga_counts_related_unclustered_headlines(fake_embed, fake_llm):
    saga = find_sagas(*frames())[0]
    assert saga['related'] == 1  # 'Cornell students protest ruling', not the tuition one
    assert saga['outlets'] == 4  # NYT, Fox, CNN from the stories plus the Daily Beast's related headline


def test_similar_stories_without_shared_word_stay_apart(fake_embed, fake_llm):
    # The Ukraine story is about as close to the Cornell ones as they are to each other, but shares no word
    for saga in find_sagas(*frames()).values():
        assert 2 not in saga['clusters']


def test_shared_word_but_distant_stories_stay_apart(fake_embed, fake_llm):
    rows = [r for r in ROWS if r[2] in (0, 3)]
    rows.append(('Cornell fraternity faces charges', 'AP', 3))  # gives story 3 the word but not the meaning
    assert find_sagas(*frames(rows)) == {}


def test_single_stories_are_not_sagas(fake_embed, fake_llm):
    rows = [r for r in ROWS if r[2] in (0, 3, -1)]
    assert find_sagas(*frames(rows)) == {}
    assert fake_llm == []  # no saga, no naming


def test_common_words_are_not_distinctive(fake_embed, fake_llm, monkeypatch):
    # At the real 4% cap, 'cornell' (in 5 of 10 headlines) is too common to link stories
    monkeypatch.setattr(sagas, 'NAME_MAX_SHARE', 0.04)
    assert find_sagas(*frames()) == {}


def test_any_similarity_still_needs_a_shared_word(fake_embed, fake_llm, monkeypatch):
    monkeypatch.setattr(sagas, 'SAGA_SIMILARITY', -1.0)
    result = find_sagas(*frames())
    assert [sorted(s['clusters']) for s in result.values()] == [[0, 1]]


def test_name_falls_back_to_biggest_storys_first_headline(monkeypatch):
    monkeypatch.setattr(sagas, '_names', {})
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: None)
    stories = pd.DataFrame({'cluster': [0, 1, 1, 1], 'title': ['Small story', 'Big one first', 'Big two', 'Big three']})
    assert sagas.name(stories, [0, 1]) == 'Big one first'


@pytest.mark.parametrize('answer', [None, {}, {'name': '  '}, {'name': '""'}])
def test_name_blank_answers_fall_back(monkeypatch, answer):
    monkeypatch.setattr(sagas, '_names', {})
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: answer)
    stories = pd.DataFrame({'cluster': [5], 'title': ['Only headline']})
    assert sagas.name(stories, [5]) == 'Only headline'


def test_name_is_truncated_and_cached(monkeypatch):
    monkeypatch.setattr(sagas, '_names', {})
    calls = []

    def complete_json(prompt, schema, max_tokens=1024):
        calls.append(prompt)
        return {'name': 'x' * 200}

    monkeypatch.setattr(llm, 'complete_json', complete_json)
    stories = pd.DataFrame({'cluster': [0, 0, 0, 0, 1], 'title': ['a1', 'a2', 'a3', 'a4', 'b1']})
    assert sagas.name(stories, [0, 1]) == 'x' * 80
    assert sagas.name(stories, [0, 1]) == 'x' * 80
    assert len(calls) == 1
    # The prompt lists up to three headlines per story
    assert '- a3' in calls[0] and '- a4' not in calls[0] and '- b1' in calls[0]


# The judge (same_saga) and the merge kept across days (_merge)

def judge(monkeypatch, tmp_path, verdicts):
    from app.analysis import sagas
    monkeypatch.setattr(sagas, 'JUDGMENTS', str(tmp_path / 'j.json'))
    asked = []

    def complete_json(prompt, schema, max_tokens=1024, model=None):
        asked.append(model)
        return {'reason': 'because', 'verdict': verdicts[len(asked) - 1]}
    monkeypatch.setattr(llm, 'complete_json', complete_json)
    return sagas, asked


def test_both_wordings_must_say_one_running_story(monkeypatch, tmp_path):
    sagas, asked = judge(monkeypatch, tmp_path, ['one running story', 'separate stories'])
    assert not sagas.same_saga(['Man bailed over RAF Fairford plot'], ['US pulls bombers from RAF Fairford'])
    assert asked == [sagas.JUDGE_MODEL, sagas.JUDGE_MODEL]
    (tmp_path / 'x').mkdir()
    sagas, asked = judge(monkeypatch, tmp_path / 'x', ['one running story', 'one running story'])
    assert sagas.same_saga(['Man bailed over RAF Fairford plot'], ['US pulls bombers from RAF Fairford'])


def test_old_verdicts_are_asked_again_but_hand_ones_kept(monkeypatch, tmp_path):
    import hashlib
    import json
    sagas, asked = judge(monkeypatch, tmp_path, ['one running story', 'one running story'])
    key = lambda a, b: hashlib.sha1(json.dumps(sorted([[a], [b]])).encode()).hexdigest()  # noqa: E731
    (tmp_path / 'j.json').write_text(json.dumps({
        key('Cornell case goes to AG', 'Hochul on Cornell'): {'same_story': False, 'model': 'qwen3:8b'},
        key('Fairford bail', 'Plot against Jews'): {'same_story': False, 'hand': True}}))
    assert sagas.same_saga(['Cornell case goes to AG'], ['Hochul on Cornell']) and len(asked) == 2
    assert not sagas.same_saga(['Fairford bail'], ['Plot against Jews']) and len(asked) == 2


def test_a_name_in_most_of_one_story_and_a_tenth_of_the_other_is_enough(monkeypatch):
    """'Fairford' in 42% of the bail story's headlines and 10% of the bombers-pulled story's (Oct 5)"""
    from app.analysis import sagas
    monkeypatch.setattr(sagas, 'same_saga', lambda a, b: True)
    a = ['Fairford man bailed'] * 4 + ['Man bailed'] * 6
    b = ['Bombers leave Fairford'] + ['Bombers leave base'] * 9
    c = ['Bombers leave base'] * 10
    for other, joined in ((b, True), (c, False)):
        titles = a + other
        groups = {'a': {'members': ['a'], 'rows': list(range(10))}, 'b': {'members': ['b'], 'rows': list(range(10, 20))}}
        vectors = np.ones((20, 2)) / np.sqrt(2)
        bags = [sagas.words(t) for t in titles]
        out = sagas._merge(groups, vectors, bags, Counter(w for bag in bags for w in bag), 100, {'fairford'}, titles)
        assert (len(out) == 1) == joined
