"""app/claim_wording.py: every claim-writing prompt gets the Brothers Grimm's winning wording (the rules read from the
person's corrections, one short plain sentence, and the person's corrections of the same kind of source)."""
from app import claim_wording as cw
from app.analysis import motif_index as mi


def test_the_examples_are_the_persons_corrections_of_the_same_kind_of_source():
    index = {'entries': {'M1': {'claims': [{'claim': 'Fixed post', 'source': 'narrative'},
                                           {'claim': 'Fixed show', 'source': 'shows'},
                                           {'claim': 'Fixed check', 'source': 'Snopes'}]}},
             'corrections': {'Loose post': 'Fixed post', 'Loose show': 'Fixed show', 'Loose check': 'Fixed check',
                             'Same': 'Same', 'Gone': 'Not in any motif'}}
    assert cw.examples('posts', index).endswith('- "Loose post" became "Fixed post"')
    assert '"Loose check" became "Fixed check"' in cw.examples('fact-checks', index)
    assert 'Loose post' not in cw.examples('shows', index) and cw.examples('Focus Group', index) == ''
    text = cw.rules('shows', index)
    assert cw.RULES in text and cw.SHORT in text and '"Loose show" became "Fixed show"' in text
    assert mi.key('x')  # the index's keys, as the corrections are matched


def test_every_claim_prompt_takes_the_wording():
    from app import narratives
    from app.analysis import factchecks, focus_group, show_claims
    w = cw.rules('posts', {'entries': {}, 'corrections': {}})
    assert cw.SHORT in narratives.PROMPT.format(posts='', genres='', chapters='', shapes='', wording=w)
    assert cw.SHORT in show_claims.PROMPT.format(show='', kind='', title='', text='', wording=w)
    assert cw.SHORT in focus_group.PROMPT.format(title='', text='', wording=w)
    assert cw.SHORT in factchecks.LABEL_PROMPT.format(source='', title='', summary='', article='', examples=w, genres='',
                                                      chapters='', shapes='')
