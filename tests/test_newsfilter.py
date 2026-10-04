"""The headline judge: ranked emotions, Borda weights, the rubric id and assess() with the llm faked out."""
import hashlib
import json
import re
from datetime import datetime as dt, timezone

import numpy as np
import pandas as pd
import pytest

from app.analysis import llm, newsfilter
from app.analysis.newsfilter import EMPTY, EMOTIONS, RUBRIC_ID, emotion_weights, ranked


# ranked()

@pytest.mark.parametrize('emotions, top, ranks', [
    (['fear', 'anger', 'sadness'], 'fear', 'fear,anger,sadness'),
    (['anger'], 'anger', 'anger'),
    (['fear', 'fear', 'anger'], 'fear', 'fear,anger'),  # duplicates collapse, order kept
    (['joy', 'hope', 'surprise', 'fear'], 'joy', 'joy,hope,surprise'),  # at most three
    (['rage', 'anger'], 'anger', 'anger'),  # unknown emotions are dropped
    ([], 'neutral', 'neutral'),
    (['bogus'], 'neutral', 'neutral'),
])
def test_ranked(emotions, top, ranks):
    assert ranked(emotions) == {'emotion': top, 'emotion_ranks': ranks}


def test_ranked_dedupes_before_capping_at_three():
    # The fourth distinct emotion would be cut, but duplicates shouldn't use up a slot
    assert ranked(['fear', 'fear', 'anger', 'anger', 'sadness'])['emotion_ranks'] == 'fear,anger,sadness'


# emotion_weights()

def test_emotion_weights_three_ranked_is_borda_3_2_1():
    weights = emotion_weights('fear,anger,sadness')
    assert weights == pytest.approx({'fear': 3 / 6, 'anger': 2 / 6, 'sadness': 1 / 6})


def test_emotion_weights_two_ranked():
    assert emotion_weights('joy,hope') == pytest.approx({'joy': 2 / 3, 'hope': 1 / 3})


def test_emotion_weights_single_emotion_gets_whole_vote():
    assert emotion_weights('neutral') == {'neutral': 1.0}


@pytest.mark.parametrize('ranks', ['fear,anger,sadness', 'joy,hope', 'surprise'])
def test_emotion_weights_sum_to_one(ranks):
    assert sum(emotion_weights(ranks).values()) == pytest.approx(1.0)


@pytest.mark.parametrize('bad', [None, '', float('nan'), 3, ['fear']])
def test_emotion_weights_bad_input_is_empty(bad):
    assert emotion_weights(bad) == {}


def test_emotion_weights_round_trips_ranked():
    weights = emotion_weights(ranked(['anger', 'disgust'])['emotion_ranks'])
    assert max(weights, key=weights.get) == 'anger'


# RUBRIC_ID and judge_id()

def test_rubric_id_is_eight_hex_chars():
    assert re.fullmatch(r'[0-9a-f]{8}', RUBRIC_ID)


def test_rubric_id_matches_prompt_and_schema_hash():
    expected = hashlib.sha1((newsfilter.PROMPT + json.dumps(newsfilter.SCHEMA, sort_keys=True)).encode()).hexdigest()
    assert RUBRIC_ID == expected[:8]


def test_rubric_id_changes_when_prompt_changes():
    changed = hashlib.sha1((newsfilter.PROMPT + ' ' + json.dumps(newsfilter.SCHEMA, sort_keys=True)).encode())
    assert changed.hexdigest()[:8] != RUBRIC_ID


def test_schema_emotions_match_constant():
    assert newsfilter.SCHEMA['properties']['emotions']['items']['enum'] == EMOTIONS
    assert set(newsfilter.EMOTION_EMOJI) == set(EMOTIONS)


@pytest.fixture
def fake_llm(monkeypatch):
    """An llm that answers from a dict keyed by headline (None for a failed call) and records its prompts."""
    answers, prompts = {}, []

    def complete_json(prompt, schema, max_tokens=1024):
        prompts.append(prompt)
        title = prompt.rsplit('Headline: ', 1)[1]
        return answers.get(title)

    monkeypatch.setattr(llm, 'backend', lambda: 'ollama')
    monkeypatch.setattr(llm, 'model', lambda: 'test-model')
    monkeypatch.setattr(llm, 'complete_json', complete_json)
    return answers, prompts


def test_judge_id_format(fake_llm):
    assert newsfilter.judge_id() == f'test-model rubric:{RUBRIC_ID}'


def test_judge_formats_prompt_with_agency_and_stripped_title(fake_llm):
    answers, prompts = fake_llm
    newsfilter.judge('  Strike kills 12  ', 'Reuters')
    assert "from Reuters's front page" in prompts[0]
    assert prompts[0].endswith('Headline: Strike kills 12')


# assess()

def judgment(**overrides):
    return {'kind': 'news', 'affected': 'residents, harmed', 'event': -2, 'loaded': 1,
            'emotions': ['fear', 'sadness'], **overrides}


def test_assess_empty_titles():
    assert newsfilter.assess([], 'X') == []


def test_assess_with_llm_scores_and_provenance(fake_llm):
    answers, _ = fake_llm
    answers['Strike kills 12'] = judgment()
    before = dt.now(timezone.utc).replace(tzinfo=None)
    [result] = newsfilter.assess(['Strike kills 12'], 'Reuters')
    assert result['news_score'] == 1.0
    assert result['event_score'] == -2.0 and isinstance(result['event_score'], float)
    assert result['loaded_score'] == 1.0
    assert result['emotion'] == 'fear'
    assert result['emotion_ranks'] == 'fear,sadness'
    assert result['scored_by'] == f'test-model rubric:{RUBRIC_ID}'
    assert isinstance(result['scored_at'], dt) and result['scored_at'].tzinfo is None
    assert before.replace(microsecond=0) <= result['scored_at'] <= dt.now(timezone.utc).replace(tzinfo=None)
    assert result['affected'] == 'residents, harmed'
    assert set(result) == set(EMPTY)


@pytest.mark.parametrize('kind, score', [('news', 1.0), ('non_news', 0.0), ('junk', 0.0)])
def test_assess_news_score_by_kind(fake_llm, kind, score):
    answers, _ = fake_llm
    answers['t'] = judgment(kind=kind)
    assert newsfilter.assess(['t'], 'A')[0]['news_score'] == score


def test_assess_truncates_affected_to_128(fake_llm):
    answers, _ = fake_llm
    answers['t'] = judgment(affected='x' * 300)
    assert newsfilter.assess(['t'], 'A')[0]['affected'] == 'x' * 128


@pytest.mark.parametrize('affected', ['', None])
def test_assess_empty_affected_is_none(fake_llm, affected):
    answers, _ = fake_llm
    answers['t'] = judgment(affected=affected)
    assert newsfilter.assess(['t'], 'A')[0]['affected'] is None


def test_assess_missing_affected_key_is_none(fake_llm):
    answers, _ = fake_llm
    r = judgment()
    del r['affected']
    answers['t'] = r
    assert newsfilter.assess(['t'], 'A')[0]['affected'] is None


def test_assess_failed_judgment_is_all_none(fake_llm):
    answers, _ = fake_llm
    answers['good'] = judgment()
    good, bad = newsfilter.assess(['good', 'bad'], 'A')
    assert bad == EMPTY
    assert all(v is None for v in bad.values())
    assert good['scored_by'] is not None


def test_assess_keeps_title_order(fake_llm):
    answers, _ = fake_llm
    titles = [f'headline {i}' for i in range(10)]
    for i, t in enumerate(titles):
        answers[t] = judgment(event=(i % 5) - 2)
    results = newsfilter.assess(titles, 'A')
    assert [r['event_score'] for r in results] == [float((i % 5) - 2) for i in range(10)]


def test_assess_results_are_independent_copies(fake_llm):
    a, b = newsfilter.assess(['x', 'y'], 'A')  # both fail
    a['news_score'] = 1.0
    assert b['news_score'] is None
    assert EMPTY['news_score'] is None


def test_assess_without_llm_or_model_returns_empty(monkeypatch):
    monkeypatch.setattr(llm, 'backend', lambda: None)
    monkeypatch.setattr(newsfilter, '_load', lambda: None)
    monkeypatch.setattr(llm, 'complete_json', lambda *a, **k: pytest.fail('llm should not be called'))
    results = newsfilter.assess(['a', 'b', 'c'], 'A')
    assert results == [EMPTY] * 3
    results[0]['news_score'] = 1.0
    assert results[1]['news_score'] is None and EMPTY['news_score'] is None


def test_assess_fallback_classifier(monkeypatch):
    class Model:
        def predict_proba(self, X):
            p = X[:, 0]
            return np.column_stack([1 - p, p])

    monkeypatch.setattr(llm, 'backend', lambda: None)
    monkeypatch.setattr(newsfilter, '_load', lambda: {'model': Model(), 'threshold': 0.3})
    monkeypatch.setattr(newsfilter, 'embed', lambda titles: np.array([[0.9], [0.1], [0.3]]))
    results = newsfilter.assess(['a', 'b', 'c'], 'A')
    assert [r['news_score'] for r in results] == [1.0, 0.0, 1.0]  # at the cutoff counts as news
    for r in results:
        assert r['scored_by'] == newsfilter.FALLBACK_JUDGE
        assert isinstance(r['scored_at'], dt)
        assert r['event_score'] is None and r['loaded_score'] is None and r['emotion'] is None
        assert r['affected'] is None


def test_rescore_outdated_only_touches_other_rubrics_and_waits_before_each_chunk(fake_llm, monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app import models
    from app.analysis import stories
    engine = create_engine('sqlite://')
    models.Base.metadata.create_all(engine)
    monkeypatch.setattr(models, 'Session', sessionmaker(bind=engine))
    monkeypatch.setattr(stories, 'refresh_story_sentiment', lambda: None)
    monkeypatch.setattr(newsfilter, 'RESCORE_CHUNK', 2)
    monkeypatch.setattr(newsfilter, 'SCORE_ARCHIVE', str(tmp_path / 'archive' / 'scores.csv'))
    answers, _ = fake_llm
    current = newsfilter.judge_id()
    with models.Session() as s:
        agency = models.Agency(name='Wire', url='https://wire.test', _bias=0, _credibility=0, _country=0)
        s.add(agency)
        for i, by in enumerate(['old rubric', 'old rubric', None, current]):
            answers[f'Headline {i}'] = {'kind': 'news', 'affected': 'x', 'event': -1, 'loaded': 1, 'emotions': ['fear']}
            article = models.Article(agency=agency, url=f'https://wire.test/{i}')
            s.add(models.Headline(article=article, title=f'Headline {i}', scored_by=by, event_score=2.0))
        s.commit()
    waits = []
    newsfilter.rescore_all(outdated=True, wait=lambda: waits.append(1))
    with models.Session() as s:
        rows = {h.title: (h.event_score, h.scored_by) for h in s.query(models.Headline)}
    assert all(rows[f'Headline {i}'] == (-1.0, current) for i in range(3))
    assert rows['Headline 3'] == (2.0, current)  # already on this rubric: left alone
    assert len(waits) == 2  # three headlines in chunks of two
    archived = pd.read_csv(tmp_path / 'archive' / 'scores.csv')
    assert sorted(archived['id']) == [1, 2, 3] and set(archived['event_score']) == {2.0}
    newsfilter.archive_scores([4])
    newsfilter.archive_scores([4])  # already archived with these scores (an interrupted run going again): not twice
    assert len(pd.read_csv(tmp_path / 'archive' / 'scores.csv')) == 4
