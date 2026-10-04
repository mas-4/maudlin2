"""Each side's wording on a story: two-word phrases one side used and the other didn't."""
from app.analysis import wording as w


def row(title, agency, bias, rated=True):
    return {'title': title, 'agency': agency, 'bias': bias, 'rated': rated}


BIG_BEND = [row('Small Texas town stopped Trump’s border wall', 'A', -1),
            row('Small Texas town stopped Trump’s wall', 'B', -2),
            row('Judge halts wall', 'C', -1),
            row('Judge pauses wall in national park', 'D', 1),
            row('National park wall paused', 'E', 2),
            row('Wall paused at national park', 'F', 1),
            row('National park wall', 'G', 0)]  # center: neither side


def test_one_sided_phrases_joined_and_ranked():
    out = w.side_phrases(BIG_BEND)
    assert [p['phrase'] for p in out['left']] == ["small texas town stopped trump's"]  # back-to-back pairs joined
    assert [p['phrase'] for p in out['right']] == ['national park', 'wall paused']  # most outlets first
    assert out['right'][0]['outlets'] == ['D', 'E', 'F']  # the center outlet doesn't count for either side


def test_needs_both_sides_represented():
    assert w.side_phrases(BIG_BEND[:3] + BIG_BEND[3:5]) == {}  # only two right-leaning outlets
    unrated = [{**r, 'rated': False} if r['bias'] > 0 else r for r in BIG_BEND]
    assert w.side_phrases(unrated) == {}


def test_shared_phrases_and_filler_never_count():
    rows = [row('Trump says wall paused', a, b) for a, b in (('A', -1), ('B', -1), ('C', -2), ('D', 1), ('E', 1),
                                                             ('F', 2))]
    assert w.side_phrases(rows) == {}  # both sides wrote it
    assert 'trump says' not in w.bigrams('Trump says wall paused') and 'wall paused' in w.bigrams('Trump says wall paused')
