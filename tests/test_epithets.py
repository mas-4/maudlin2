"""app/analysis/epithets.py: the lexicon, counting by side, and candidate mining (no database)."""
import re

import pandas as pd
import pytest

import app.analysis.epithets as ep


def frame(rows):
    df = pd.DataFrame(rows, columns=['title', 'agency', 'bias', 'rated'])
    df['side'] = [ep.side(b, r) for b, r in zip(df['bias'], df['rated'])]
    df['first'] = pd.Timestamp('2026-10-04')
    df['url'] = 'u'
    return df


def test_lexicon_is_well_formed():
    terms = ep.lexicon()
    assert len({(t['family'], t['term']) for t in terms}) == len(terms)
    for t in terms:
        assert isinstance(t['regex'], re.Pattern)
        described = '(' in t['term']  # a term named by description ("Democrat (as an adjective)")
        assert described or t['regex'].search(t['term']) or t['term'] in (
            'undocumented immigrant', 'radical Islamic terrorism', 'climate alarmism'), t['term']


@pytest.mark.parametrize('title, term', [
    ('Biden-appointed judge blocks rule', 'Biden judge'), ('ICE arrests illegal aliens', 'illegal alien'),
    ('MAGA crowd cheers', 'MAGA'), ('Embattled mayor resigns', 'embattled'),
    ('GOP blocks Democrat-led states', 'Democrat (as an adjective)'), ('The Democrat Party is over', 'Democrat (as an adjective)'),
    ('Democratic senators push bill', 'Democratic (as an adjective)'),
])
def test_terms_match_headlines(title, term):
    [entry] = [t for t in ep.lexicon() if t['term'] == term]
    assert entry['regex'].search(title)


def test_count_by_side_and_outlet():
    df = frame([('ICE arrests illegal aliens', 'Breitbart', 2, True), ('Illegal alien charged', 'Fox News', 1, True),
                ('Undocumented workers march', 'CNN', -1, True), ('Weather is fine', 'AP', 0, True)])
    terms = [t for t in ep.lexicon() if t['family'] == 'People who entered illegally']
    [fam] = ep.count(df, terms)
    alien = next(t for t in fam['terms'] if t['term'] == 'illegal alien')
    assert (alien['total'], alien['right'], alien['left']) == (2, 2, 0)
    assert {o['name'] for o in alien['outlets']} == {'Breitbart', 'Fox News'}
    assert fam['terms'][0]['total'] >= fam['terms'][-1]['total']


def test_mining_needs_several_outlets_and_skips_outlet_names():
    rows = [(f'Trump voters rally in town {i}', f'Left {i}', -1, True) for i in range(3)]
    rows += [('Matt Vespa writes again today', 'Townhall', 1, True)] * 6  # one outlet's byline
    rows += [('Fox News reports fox news thing', 'Fox News', 1, True)] * 2
    rows += [(f'Unrelated item number {i}', f'Right {i}', 1, True) for i in range(5)]
    phrases = {c['phrase'] for c in ep.mine_candidates(frame(rows), min_count=1)}
    assert 'trump voters' in phrases
    assert 'matt vespa' not in phrases and 'fox news' not in phrases


def test_democrat_adjective_ignores_the_noun():
    [entry] = [t for t in ep.lexicon() if t['term'] == 'Democrat (as an adjective)']
    assert not entry['regex'].search('A Democrat in Ohio wins') and not entry['regex'].search('Democrats rally')
