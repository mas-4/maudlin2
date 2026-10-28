"""The outlet fingerprints (app.analysis.outlet_profile): the coverage axes keep their direction whatever sign the maths
hands back, nearest neighbours, type naming and its guard on ratings, the whole profile on a made-up month of front
pages, and the day's cache."""
from datetime import datetime as dt, timedelta as td

import numpy as np
import pandas as pd
import pytest

from app.analysis import outlet_profile as op

UNTIL = dt(2026, 10, 28, 12)


def planted(seed: int = 0) -> tuple[pd.DataFrame, pd.Series]:
    """A 0/1 outlets × stories table with business desks, a mainstream, and left and right outlets who share the
    political fight's stories and each have their own"""
    rng = np.random.default_rng(seed)
    groups = {'biz': (0, 6), 'mid': (-1, 8), 'left': (-2, 6), 'right': (2, 6)}
    stories = {'shared': 30, 'biz': 25, 'fight': 30, 'left': 12, 'right': 12}
    takes = {'biz': {'shared': .6, 'biz': .8}, 'mid': {'shared': .8, 'biz': .2, 'fight': .3, 'left': .1, 'right': .1},
             'left': {'shared': .4, 'fight': .8, 'left': .8}, 'right': {'shared': .4, 'fight': .8, 'right': .8}}
    cols = [f'{k}{i}' for k, n in stories.items() for i in range(n)]
    rows, bias = {}, {}
    for g, (b, n) in groups.items():
        for i in range(n):
            p = np.array([takes[g].get(c.rstrip('0123456789'), .03) for c in cols])
            rows[f'{g}{i}'] = (rng.random(len(cols)) < p).astype(float)
            bias[f'{g}{i}'] = b
    return pd.DataFrame(rows, index=cols).T, pd.Series(bias)


def axes(X: pd.DataFrame, bias: pd.Series) -> pd.DataFrame:
    rows, cols, _ = op.correspondence(X)
    return op.orient(rows, cols, bias)[0]


def test_orient_puts_the_fight_right_and_the_left_up():
    X, bias = planted()
    rows = axes(X, bias)
    group = rows.groupby(rows.index.str.rstrip('0123456789')).mean()
    assert group.loc['left', 'ca1'] > group.loc['biz', 'ca1'] and group.loc['right', 'ca1'] > group.loc['biz', 'ca1']
    assert group.loc['left', 'ca2'] > group.loc['right', 'ca2']


def test_orient_ignores_the_sign_and_the_order_the_maths_hands_back():
    X, bias = planted()
    rows, cols, _ = op.correspondence(X)
    a = op.orient(rows, cols, bias)[0]
    b = op.orient(-rows, -cols, bias)[0]  # the same axes, flipped
    pd.testing.assert_frame_equal(a, b)
    rng = np.random.default_rng(3)
    shuffled = X.iloc[rng.permutation(len(X)), rng.permutation(X.shape[1])]
    c = axes(shuffled, bias).loc[a.index]
    np.testing.assert_allclose(c.to_numpy(), a.to_numpy(), atol=1e-9)


@pytest.mark.parametrize('seed', [1, 2, 3, 4])
def test_orient_holds_from_one_month_to_the_next(seed):
    """Fresh draws of the same world (a new month's stories) land the same way round"""
    X, bias = planted(seed)
    rows = axes(X, bias)
    group = rows.groupby(rows.index.str.rstrip('0123456789')).mean()
    assert group.loc['right', 'ca1'] > 0 > group.loc['biz', 'ca1']
    assert group.loc['left', 'ca2'] > 0 > group.loc['right', 'ca2']


def test_orient_without_ratings_still_picks_a_side():
    X, bias = planted()
    rows, cols, _ = op.correspondence(X)
    a = op.orient(rows, cols, pd.Series(dtype=float))[0]
    b = op.orient(-rows, -cols, pd.Series(dtype=float))[0]
    pd.testing.assert_frame_equal(a, b)


def test_nearest_lists_the_closest_others_first():
    Z = pd.DataFrame({'a': [0, 1, 2, 10, 11, 1]}, index=['p', 'q', 'r', 's', 't', 'u'])
    near = op.nearest(Z, 3)
    assert near['p'] == ['q', 'u', 'r']  # q and u tie at 1: by name
    assert near['s'] == ['t', 'r', 'q']
    assert all(name not in others for name, others in near.items())
    assert all(len(others) == 3 for others in near.values())


def test_a_cluster_two_names_claim_gets_neither():
    labels = pd.Series([1, 1, 1, 1, 2, 2], index=['L1', 'L2', 'R1', 'R2', 'B1', 'B2'])
    anchors = {'Left': ['L1', 'L2'], 'Right': ['R1', 'R2'], 'Biz': ['B1', 'B2', 'missing']}
    assert op.name_clusters(labels, anchors) == {2: 'Biz'}
    labels['R1'] = labels['R2'] = 3
    assert op.name_clusters(labels, anchors) == {1: 'Left', 3: 'Right', 2: 'Biz'}
    # more than half of the anchors present, or no name
    assert op.name_clusters(pd.Series([1, 2], index=['L1', 'L2']), {'Left': ['L1', 'L2']}) == {}


def test_a_side_named_type_never_contradicts_a_rating():
    found = {'Left opinion': {'members': ['a', 'b']}, 'Left partisan web': {'members': ['a', 'b', 'c']},
             'Outside the partisan webs': {'members': ['d']}}
    assert op._type_of('a', found, -2) == 'Left opinion'  # the smallest type holding it
    assert op._type_of('b', found, float('nan')) == 'Left opinion'  # not rated
    assert op._type_of('a', found, 1) is None  # rated right: no left type
    assert op._type_of('c', found, 0) is None  # rated center
    assert op._type_of('d', found, 2) == 'Outside the partisan webs'


def month(seed: int = 0) -> dict:
    """A made-up month of front pages in load()'s shape: the planted coverage, a headline per story an outlet ran
    (the left and right ones heated, the business desks plain), filler headlines, and the wires"""
    rng = np.random.default_rng(seed)
    X, bias = planted(seed)
    X.loc['AP'] = (rng.random(X.shape[1]) < .5).astype(float)
    X.loc['Reuters'] = (rng.random(X.shape[1]) < .5).astype(float)
    bias['AP'], bias['Reuters'] = -1, 0
    t0 = UNTIL - td(days=20)
    start = {s: t0 + td(hours=int(h)) for s, h in zip(X.columns, rng.integers(0, 20 * 24, X.shape[1]))}
    heads, links = [], []
    style = {'left': 'slams furious Trump MAGA', 'right': 'slams shocking leftists', 'biz': 'shares rise in markets',
             'mid': 'officials say', 'AP': 'officials say', 'Reuters': 'officials say'}
    article = 0
    for outlet, row in X.iterrows():
        kind = outlet.rstrip('0123456789')
        loaded = 1.5 if kind in ('left', 'right') else 0.2
        for s in row.index[row > 0]:
            article += 1
            t = start[s] + td(hours=int(rng.integers(0, 12)))
            heads.append({'id': article, 'article_id': article, 'title': f'Story {s} news {style[kind]}', 'hfa': t,
                          'hla': t + td(hours=6), 'news': 0.9, 'event': -0.5, 'loaded': loaded, 'vader': 0.0,
                          'emotion': 'anger' if loaded > 1 else 'neutral', 'url': f'https://x/{article}', 'name': outlet})
            links.append({'story_id': s, 'id': article})
        for i in range(110):
            article += 1
            t = t0 + td(hours=int(rng.integers(0, 20 * 24)))
            heads.append({'id': article, 'article_id': article, 'title': f'Item {i} {outlet} {style[kind]}', 'hfa': t,
                          'hla': t + td(hours=3), 'news': 0.8, 'event': 0.0, 'loaded': loaded, 'vader': 0.0,
                          'emotion': 'neutral', 'url': f'https://x/{article}', 'name': outlet})
    return {'heads': pd.DataFrame(heads), 'links': pd.DataFrame(links),
            'outlets': pd.DataFrame({'name': bias.index, 'bias': bias.values, 'rated': True}),
            'labels': pd.DataFrame({'story_id': X.columns, 'label': [f'Label <{s}>' for s in X.columns]})}


@pytest.fixture(scope='module')
def built():
    return op.build(month(), UNTIL)


def test_the_profile_covers_every_outlet_with_enough_stories(built):
    outlets = built['outlets']
    assert len(outlets) == 28  # 26 planted and the two wires
    for name, o in outlets.items():
        assert 0 <= o['wire_pct'] <= 100 and 0 <= o['heat_pct'] <= 100
        assert len(o['like']) == op.NEIGHBOURS and name not in o['like']
        assert set(o['like']) <= set(outlets)
    assert outlets['AP']['is_wire'] and not outlets['biz0']['is_wire']
    assert built['window_days'] == op.WINDOW_DAYS and built['stories'] > 50


def test_the_profile_finds_the_behaviour_it_was_given(built):
    o = built['outlets']
    mean = lambda kind, key: np.mean([v[key] for n, v in o.items() if n.rstrip('0123456789') == kind])  # noqa: E731
    assert mean('left', 'heat_pct') > mean('biz', 'heat_pct') and mean('right', 'heat_pct') > mean('mid', 'heat_pct')
    assert mean('right', 'x') > mean('biz', 'x') and mean('left', 'y') > mean('right', 'y')
    # the look-alikes of a left outlet are left outlets
    assert all(n.startswith('left') for n in o['left0']['like'])
    assert all(n.startswith('right') for n in o['right0']['like'])
    ends = built['axes']['x']
    assert any('biz' in s for s in ends['low']) and all(s.startswith('Label <') for s in ends['low'] + ends['high'])


def test_the_profile_is_kept_for_the_day(monkeypatch, tmp_path):
    monkeypatch.setattr(op, 'CACHE', str(tmp_path / 'outlet_profile.json'))
    calls = []
    monkeypatch.setattr(op, 'load', lambda since, con=None: calls.append(since) or {'heads': None})
    monkeypatch.setattr(op, 'build', lambda data, until: {'outlets': {'x': {}}, 'stories': 1})
    assert op.profiles(now=UNTIL) == {'outlets': {'x': {}}, 'stories': 1}
    op.profiles(now=UNTIL + td(hours=5))
    assert len(calls) == 1 and calls[0] == UNTIL - td(days=op.WINDOW_DAYS)
    op.profiles(now=UNTIL + td(days=1))  # a new day
    assert len(calls) == 2


def test_an_outlet_whose_look_alikes_are_elsewhere_shows_no_type():
    """Oct 28, the person, of One America News Network shown as "wire and mainstream" beside its right-wing look-alikes:
    "doesn't this seem wrong to you?\""""
    first = {'OAN': ('Outside the partisan webs', None), 'JTN': ('Outside the partisan webs', None),
             'WJ': ('Right partisan web', 'Right partisan web'), 'DC': ('Right partisan web', 'Right partisan web'),
             'AP': ('Outside the partisan webs', None), 'Reuters': ('Outside the partisan webs', None)}
    like = {'OAN': ['JTN', 'WJ', 'DC'], 'AP': ['Reuters', 'JTN', 'WJ'], 'WJ': ['DC', 'OAN', 'AP']}
    assert op.agreed('OAN', 0, first, like) is None  # one of three agrees: on the edge, no type
    assert op.agreed('AP', 0, first, like) == 'Outside the partisan webs'  # two of three
    assert op.agreed('WJ', 1, first, like) is None and op.agreed('WJ', 0, first, like) is None
