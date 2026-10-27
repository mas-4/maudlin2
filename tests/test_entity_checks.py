"""Who's in the news, after the Oct 27 audit: names the headlines name in full, roles that aren't names, one subject
under one name."""
from app.analysis import entities as en


def test_a_name_must_be_named_in_full_on_word_boundaries():
    assert en.named_fully('Houthis', 'houthi rebels strike')
    assert not en.named_fully('Joe Vance', 'vance says')  # a first name nobody wrote
    assert not en.named_fully('Federal Bureau of Investigation', 'federal officials say')
    assert not en.named_in('Anne Carson', 'a new channel')  # inside another word


def test_roles_and_plurals_are_not_names_but_named_institutions_are():
    for role in ('Students', 'Convicted murderer', 'Serbian president', 'National Defence', 'Illinois man', 'Opposition'):
        assert en.generic(role), role
    for name in ('Supreme Court', 'White House', 'Ilhan Omar', 'Justice Department', 'Pope Leo'):
        assert not en.generic(name), name


def test_variants_go_by_one_name_and_overreaching_aliases_are_off():
    aliases = en.load_aliases()['aliases']
    assert {en.canonical(n, aliases) for n in ('DOJ', 'Department of Justice', 'Justice Department')} == {'Justice Department'}
    assert en.canonical('administration', aliases) == 'administration'  # Cornell's isn't the Trump administration


def test_a_surname_joins_the_one_full_name_it_belongs_to():
    names = {'putin': {'name': 'Putin', 'stories': [{'id': 1}], 'outlets': {'A': 'left'}},
             'vladimir putin': {'name': 'Vladimir Putin', 'stories': [{'id': 2}], 'outlets': {'B': 'right'}},
             'biden': {'name': 'Biden', 'stories': [{'id': 3}], 'outlets': {}},
             'joe biden': {'name': 'Joe Biden', 'stories': [], 'outlets': {}},
             'hunter biden': {'name': 'Hunter Biden', 'stories': [], 'outlets': {}}}
    en.merge_surnames(names)
    assert 'putin' not in names and [s['id'] for s in names['vladimir putin']['stories']] == [2, 1]
    assert 'biden' in names  # two Bidens: left alone


def test_rallies_in_different_states_are_never_linked():
    import numpy as np
    from app.analysis import clustering as c
    titles = ['Trump Participates in Midterm Rally in Mississippi', 'Trump Participates in Midterm Rally in Michigan',
              'Trump rallies Mississippi voters', 'Comey charged again']
    sim = c.unlink_place_conflicts(np.full((4, 4), 0.9), titles)
    assert sim[0, 1] == 0 and sim[1, 0] == 0  # Mississippi and Michigan stay apart
    assert sim[0, 2] == 0.9 and sim[0, 3] == 0.9  # the same state, or a headline with no rally, are left alone
    assert c.places('Michigan judge rules') == set()  # a state without a rally or campaign stop isn't a place here
