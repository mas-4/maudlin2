"""The site redo, Oct 28, group C: the outlets page's paired leaderboards and table (colored by outlet-map type, lean a
small mark), the outlet map's lists (the stories that pull each way, by which side ran them more; the types as
strips), and the outlet pages' front page in two, feelings against the average outlet and measures against the
median."""
import glob
import re

import pandas as pd
from bs4 import BeautifulSoup

from app.site import page_outlet_map as om
from app.site import page_outlets as po
from app.site.boards import LEAN_INK
from tests.test_site_pages_render import OUTLET_PROFILE, site  # noqa: F401 - the rendered scratch site, a fixture


# ---- the pieces

def test_side_look_names_the_side_that_ran_a_story_more():
    assert om.side_look(0.6, 0.1)['ink'] == LEAN_INK['left']
    assert om.side_look(0.1, 0.6)['ink'] == LEAN_INK['right']
    assert om.side_look(0.5, 0.45)['ink'] == LEAN_INK['center']  # alike
    assert om.side_look(None, None)['mark'] == '⚖️'


def test_types_keep_their_own_colors_and_the_unsettled_are_white():
    assert om.type_look({'type': 'Right partisan web'})['ink'] == om.TYPE_INK['Right partisan web']
    assert om.type_look({'type': None}) is om.NO_TYPE and om.NO_TYPE['ink'] == '#ffffff'
    assert om.type_look(None) is om.OFF_MAP
    # no type is drawn in the lean blue or red
    assert not set(om.TYPE_INK.values()) & {LEAN_INK[k] for k in ('left', 'lean left', 'lean right', 'right')}
    key = om.type_key({'Left opinion', 'Outside the partisan webs', None}, off_map=True)
    assert [k['name'] for k in key] == ['Outside the partisan webs', 'Left opinion', 'No settled type',
                                        'Not on the map']  # the fixed order, whatever order they came in


def test_pull_boards_pair_the_ends_and_link_stories_with_pages():
    profile = {'outlets': dict.fromkeys('abcd', {}), 'axes': {'pull': {
        'x': {'low': [{'id': 1, 'label': 'Markets <up>', 'outlets': 3, 'left': 0.2, 'right': 0.1}],
              'high': [{'id': 2, 'label': 'A fight', 'outlets': 4, 'left': 0.1, 'right': 0.9}]},
        'y': {'low': [], 'high': [{'id': 3, 'label': 'A probe', 'outlets': 2, 'left': 0.8, 'right': 0.0}]}}}}
    (left, right), (up, down) = om.pull_boards(profile, with_page={1, 3})
    assert left['rows'][0]['href'] == 'story-1.html' and right['rows'][0]['href'] is None  # no page, no link
    assert right['rows'][0]['ink'] == LEAN_INK['right'] and up['rows'][0]['ink'] == LEAN_INK['left']
    assert left['rows'][0]['figure'] == '3 of 4' and down['rows'] == []
    # a profile from before the stories carried ids still lists the labels
    old = {'outlets': {}, 'axes': {'x': {'low': ['Old'], 'high': []}, 'y': {'low': [], 'high': []}}}
    assert om.pull_boards(old, set())[0][0]['rows'][0]['name'] == 'Old'


def test_feeling_strip_reads_against_the_average_outlet():
    from app.analysis.newsfilter import EMOTIONS
    average = dict.fromkeys(EMOTIONS, 10.0)
    mine = {**average, 'anger': 25.0, 'hope': 2.0, 'fear': 11.0}
    strip = po.feeling_strip(mine, average)
    assert strip['more']['name'] == 'anger' and strip['less']['name'] == 'hope'
    rows = {r['name']: r for r in strip['rows']}
    assert rows['anger']['diff'] == 15 and rows['anger']['bar'] == 100 and rows['fear']['side'] == 'even'
    assert strip['rows'][0]['name'] == 'anger' and strip['rows'][-1]['name'] == 'hope'
    assert po.feeling_strip(None, average) is None


def test_versus_says_how_far_from_the_median():
    assert po.versus(7.1, 2.0, 10, ' per 100')['words'] == '3.5× the median'
    assert po.versus(4.0, 2.0, 10, '')['words'] == '2× the median'
    assert po.versus(2.05, 2.0, 10, '')['words'] == 'about the median'
    assert po.versus(1.0, 4.0, 10, '')['words'] == '25% of the median'
    v = po.versus(5, 10, 20, '%')
    assert v['bar'] == 25 and v['tick'] == 50
    assert po.versus(None, 2, 10, '') is None


def test_front_page_splits_the_pack_from_its_own():
    live = pd.DataFrame([
        {'agency': 'Us', 'url': 'u1', 'title': 'Ours, big story', 'position': 2, 'bias': 0, 'rated': True},
        {'agency': 'Us', 'url': 'u2', 'title': 'Only ours', 'position': 1, 'bias': 0, 'rated': True},
        {'agency': 'Us', 'url': 'u3', 'title': 'Ours, small story', 'position': 3, 'bias': 0, 'rated': True},
        {'agency': 'L', 'url': 'l1', 'title': 'x', 'position': 1, 'bias': -2, 'rated': True},
        {'agency': 'R', 'url': 'r1', 'title': 'y', 'position': 1, 'bias': 2, 'rated': True},
    ])
    story_of_url = {'u1': ('big', 'Big story'), 'l1': ('big', 'Big story'), 'r1': ('big', 'Big story'),
                    'u3': ('small', 'Small story')}
    now = po.front_page(live[live['agency'] == 'Us'], live, story_of_url)
    assert [h['title'] for h in now['pack']] == ['Ours, big story', 'Ours, small story']
    assert [h['rank'] for h in now['pack']] == [1, 2] and now['pack'][0]['outlets'] == 3
    assert now['pack'][0]['split'] == 50  # one left-rated, one right-rated
    assert now['pack'][1]['split'] is None  # only a center outlet
    assert now['only'] == [{'title': 'Only ours', 'url': 'u2', 'place': 1}]


# ---- the pages

def test_outlets_page_leads_with_paired_boards_colored_by_type(site):  # noqa: F811
    page = site['soup']['agencies.html']
    keys = [s['class'][1].removeprefix('rank-board-') for s in page.select('.rank-boards > .rank-board')]
    assert keys == ['spiciest', 'plainest', 'grimmest', 'sunniest', 'rewrites', 'never', 'wire', 'own']
    assert not page.select('.outlet-card') and not page.select('.lineup')  # no masonry, no chip columns
    rows = page.select('.orow')
    assert rows and all(r.select_one('.olean') is not None for r in rows)  # the lean, a small mark
    # every row's card is on the page, and every outlet is reachable from the table
    table = page.select('table.olist tbody tr')
    slugs = {tr['id'].removeprefix('outlet-') for tr in table}
    assert {r['data-ocard'] for r in rows} <= slugs
    assert all(page.select_one(f'template#ocard-{s}') is not None for s in slugs)
    profiled = set(OUTLET_PROFILE['outlets'])
    for tr in table:
        mark = tr.select_one('.ocell-mark')
        if tr['data-name'] not in profiled:
            assert mark['aria-label'] == 'Not on the map'
    assert page.select_one('#outlet-search') is not None
    assert not page.select('.rank-boards [title], table.olist [title]')  # hover cards, no tooltips


def test_outlet_map_lists(site):  # noqa: F811
    page = site['soup']['outlet-map.html']
    boards = [s['class'][1] for s in page.select('.rank-board')]
    assert boards == ['rank-board-pull-left', 'rank-board-pull-right', 'rank-board-pull-up', 'rank-board-pull-down']
    assert page.select_one('details.omap-how') is not None
    plain = page.get_text(' ')
    how = page.select_one('details.omap-how').get_text(' ')
    assert 'correspondence analysis' in how and plain.count('correspondence analysis') == how.count('correspondence analysis')
    assert '% the same' not in plain
    assert page.select('.omap-type-row .rank-bar') and not page.select('.omap-members')
    assert page.select('table.omap-table .ocell-bar')


def test_outlet_pages_split_the_front_page_and_compare(site):  # noqa: F811
    pages = glob.glob(str(site['build'] / 'outlet-*.html'))
    seen_pack = seen_only = seen_feel = seen_vs = False
    for p in pages:
        if p.endswith('outlet-map.html'):
            continue
        with open(p, encoding='utf-8') as f:
            soup = BeautifulSoup(f.read(), 'html.parser')
        seen_pack |= bool(soup.select('#now-pack ~ .onow-list .onow-story, #now-pack ~ .rank-list .onow-story'))
        seen_only |= bool(soup.select('.onow-only'))
        seen_feel |= bool(soup.select('.ofeel-row'))
        seen_vs |= bool(soup.select('.ovs-row .ovs-tick'))
        assert not soup.select('.feeling-bar') and not soup.select('ol.outlet-now')
        for row in soup.select('.ovs-figure'):
            assert re.search(r'median', row.get_text())
    assert seen_pack and seen_only and seen_feel and seen_vs


def test_the_leaderboards_hold_us_and_uk_outlets_only():
    """Oct 28: on the whole list Plainest and Least wire copy filled with outlets abroad we never match to the wires"""
    from app.site import page_agencies as pa
    from app.utils.constants import Country
    def outlet(name, country):
        return {'name': name, 'slug': name.lower(), 'country': str(country), 'shares': dict.fromkeys(('stirs', 'plain', 'grim', 'sunny'), 50),
                'edits': 1, 'headlines': 100, 'wire': 0, 'look': {'ink': '#fff', 'mark': '•', 'name': 'x'}, 'lean_look': {}}
    pairs = pa.outlet_boards([outlet('Fox', Country.us), outlet('BBC', Country.gb), outlet('Xinhua', Country.cn)], 30)
    names = {r['name'] for pair in pairs for b in pair for r in b['rows']}
    assert 'Xinhua' not in names and {'Fox', 'BBC'} <= names
