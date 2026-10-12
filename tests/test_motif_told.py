import numpy as np

from app.analysis import motif_index as mi, motif_told as mt


def kept(text, source='narrative', ref='', date='2026-10-01'):
    return {'claim': text, 'source': source, 'ref': ref, 'date': date, 'checked': 'yes'}


def test_one_case_told_many_ways_is_one_occasion():
    claims = [kept('Cornell University let seven students off with essays'),
              kept('A woman sued Cornell University and seven students', 'Snopes', 'https://snopes.com/a'),
              kept('The mayor of Springfield took bribes from a builder')]
    named = mt.telling_names([c['claim'] for c in claims])
    vec = {c['claim']: v for c, v in zip(claims, np.eye(3))}  # none reads like another
    got = mt.occasions(claims, vec, named)
    assert sorted(len(g) for g in got) == [1, 2]  # Cornell joins its two; Springfield is apart


def test_a_common_word_or_one_source_joins_nothing_or_everything_rightly():
    claims = [kept('Republican leaders in Ohio hid the report', 'PolitiFact', 'https://p/1'),
              kept('A Republican senator lied about the vote', 'PolitiFact', 'https://p/2'),
              kept('The video is fake', 'PolitiFact', 'https://p/1')]
    named = mt.telling_names([c['claim'] for c in claims] + ['the republican party'])
    assert all('Republican' not in s for s in named.values())  # used in lower case too: says nothing
    vec = {c['claim']: v for c, v in zip(claims, np.eye(3))}
    assert sorted(len(g) for g in mt.occasions(claims, vec, named)) == [1, 2]  # the two from one fact-check join


def test_told_is_kept_on_entries_and_decides_attested(monkeypatch, tmp_path):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    mi.save({'next': 3, 'claims': {}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Campus', 'claims': [kept('Students say Cornell hid it'), kept('Critics say Cornell lied', date='2026-10-05')]},
        'M002': {'id': 'M002', 'name': 'Graft', 'claims': [kept('Paxton took bribes'), kept('A mayor took a bribe'),
                                                            {'claim': 'unchecked', 'source': 'narrative'}]}}})
    assert mi.attested(mi.load()['entries']['M001'])  # before the first count: two kept claims
    from app import narratives
    monkeypatch.setattr(narratives, 'embed', lambda texts: np.eye(len(texts)))
    mt.refresh()
    es = mi.load()['entries']
    assert es['M001']['told']['events'] == 1 and es['M001']['told']['span'] == ['2026-10-01', '2026-10-05']
    assert es['M002']['told']['events'] == 2  # the unchecked filing isn't counted
    assert not mi.attested(es['M001']) and mi.attested(es['M002'])


def test_one_news_story_is_one_occasion_but_one_issue_isnt():
    claims = [kept('the mayor took bribes', 'narrative') | {'story': 7, 'story_tie': 'same event'},
              kept('a builder paid off city hall', 'Snopes', 'https://s/1') | {'story': 9},
              kept('corruption is everywhere', 'narrative') | {'story': 7, 'story_tie': 'same issue'}]
    named = mt.telling_names([c['claim'] for c in claims])
    vec = {c['claim']: v for c, v in zip(claims, np.eye(3))}
    assert sorted(len(g) for g in mt.occasions(claims, vec, named, {9: 7})) == [1, 2]  # story 9 was merged into 7
