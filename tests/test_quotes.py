"""app/analysis/quotes.py: quoted phrases in headlines and per-story quote selection."""
import pytest

from app.analysis import quotes as q


@pytest.mark.parametrize('title, expected', [
    ("Trump's 'slush fund' sends $90 to seniors", ['slush fund']),
    ('Trump hails “wonderful seniors” as checks go out', ['wonderful seniors']),
    ('He said "we were never going to do it" on Friday', ['we were never going to do it']),
    ("Trump's plan isn't working, says expert", []),  # apostrophes aren't quotes
    ("Strikes on ‘military targets’ in Sanaa", ['military targets']),
    ("'SHARDS' and 'love letter': two takes", ['SHARDS', 'love letter']),
])
def test_quoted(title, expected):
    assert q.quoted(title) == expected


def row(agency, bias, title, rated=True):
    return {'agency': agency, 'bias': bias, 'rated': rated, 'title': title}


def test_story_quotes_by_side():
    rows = [row('MSNBC', -2, "Trump's 'slush fund' checks"), row('HuffPost', -2, 'Inside the "slush fund"'),
            row('Fox News', 1, 'Trump hails ‘wonderful seniors’'), row('AP', 0, 'Checks go out'),
            row('Puck', 0, "A 'slush fund', critics say", rated=False)]
    out = q.story_quotes(rows)
    assert out[0]['phrase'].lower() == 'slush fund' and out[0]['count'] == 3
    assert (out[0]['left'], out[0]['unrated'], out[0]['lead']) == (2, 1, 'left')
    assert out[1]['phrase'] == 'wonderful seniors' and out[1]['lead'] == 'right'


def test_ties_are_mixed_and_cards_are_capped():
    rows = [row('A', -1, "'x y'"), row('B', 1, "'x y'")] + [row(f'O{i}', 0, f"'phrase {i}'") for i in range(6)]
    out = q.story_quotes(rows)
    assert out[0]['lead'] == 'mixed' and len(out) == q.MAX_ON_CARD


def test_quotes_inside_one_another_are_one_chip():
    rows = [row('A', -1, "Altman: 'Bad Things' ahead"), row('B', 1, "'the world should accept some bad things happening'"),
            row('C', 0, "'world should accept some bad things'"), row('D', 1, "'Super Intelligence Force'"),
            row('E', -1, "'Super Intelligence Force' unveiled"), row('F', 0, "a 'Super Intelligence' push"),
            row('G', 0, "'SpaceXSI' and 'SI'")]
    out = {o['phrase']: o for o in q.story_quotes(rows)}
    whole = out['the world should accept some bad things happening']  # a tie: the longer wording shows
    assert whole['count'] == 3 and len(whole['variants']) == 2
    assert out['Super Intelligence Force']['count'] == 3 and out['Super Intelligence Force']['variants'] == ['Super Intelligence']
    assert 'SI' in out and 'SpaceXSI' in out  # whole words only
