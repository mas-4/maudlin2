"""The Play page's games (app/analysis/play.py, app/site/page_play.py): residue stripping, the daily picks, scoring
and the two-papers card"""
import json
import re
import shutil
import subprocess

import pytest
from bs4 import BeautifulSoup
from PIL import Image

from app.analysis import play
from app.site import page_play, share_images
from app.site.common import j2env, TemplateHandler
from app.utils.config import Config


# <editor-fold desc="residue">
@pytest.mark.parametrize('raw, outlet, want', [
    ('Trump signs order 3 hours ago', 'X', 'Trump signs order'),
    ('WATCH: Senator storms out of hearing', 'X', 'Senator storms out of hearing'),
    ('POLITICS | House passes the bill', 'X', 'House passes the bill'),
    ('Storm hits coast via Getty Images', 'X', 'Storm hits coast'),
    ('68.2K views Governor signs the budget', 'X', 'Governor signs the budget'),
    ('Stocks Climb as Oil Falls: Markets Wrap', 'Bloomberg', 'Stocks Climb as Oil Falls'),
    ('1 Trending: The Plan Nobody Saw Coming', 'X', 'The Plan Nobody Saw Coming'),
    ('Judge Blocks the Rule Amy Curtis', 'Townhall', 'Judge Blocks the Rule'),
    ('Judge Blocks the Rule Susie Moore Continue Reading', 'Red State', 'Judge Blocks the Rule'),
    ('U.S. News FTC sues Dollar General Scripps', 'Scripps News', 'FTC sues Dollar General'),
    ('Amy Curtis wins an award', 'Townhall', 'Amy Curtis wins an award'),  # a name that isn't at the end stays
])
def test_clean_strips_residue(raw, outlet, want):
    names = {'Townhall': {'Amy Curtis'}, 'Red State': {'Susie Moore', 'Continue Reading'}}
    assert play.clean(raw, outlet, names) == want


def test_bylines_are_names_that_end_an_outlets_headlines():
    rows = [('Townhall', f'Story number {i} about things Amy Curtis') for i in range(9)]
    rows += [('Red State', f'Item {i} on the news Susie Moore Continue Reading') for i in range(9)]
    rows += [('AP', f'Officials at the White House meet {i}') for i in range(5)]
    rows += [('AP', 'Talks held at the White House') for _ in range(9)]  # ends 9, but used elsewhere too
    found = play.bylines(rows)
    assert found['Townhall'] == {'Amy Curtis'}
    assert found['Red State'] == {'Continue Reading', 'Susie Moore'}  # the name under the glued-on pair
    assert 'White House' not in found['AP']


def test_puzzles_leave_out_offensive_and_non_headlines():
    assert play.fit_for_puzzle('Senate passes the farm bill after a long night of talks')
    assert not play.fit_for_puzzle('Man shot outside a bar after a long night of drinking')
    assert not play.fit_for_puzzle('Cartoon: the week in politics as drawn by our artist')
    assert not play.fit_for_puzzle('Too short')
    assert not play.fit_for_puzzle('Fox News host says the bill is good for farmers',
                                   play.outlet_names_re(['Fox News']))
# </editor-fold>


# <editor-fold desc="the daily picks">
WORDS = ('mayor goat parade', 'pastor potluck choir', 'senate budget clock', 'harbor ferry strike', 'pumpkin carver prize',
         'museum heist painting', 'school lunch menu', 'airport runway delay', 'river flood barrier', 'bakery bread queue',
         'stadium roof repair', 'library fines amnesty', 'garden snail census', 'tunnel boring machine', 'bridge toll hike')


def satire_pool():
    """Each title its own words, so none are kept apart for sharing a topic"""
    sat = [{'title': f'{WORDS[i]} joke', 'outlet': f'Left satire {i % 3}', 'group': 'left', 'p': i / 20}
           for i in range(10)]
    sat += [{'title': f'{WORDS[10 + i]} gag', 'outlet': 'The Babylon Bee', 'group': 'right', 'p': i / 10}
            for i in range(4)]
    real = [{'title': f'{a} {b} news'.replace(' ', f' {i} ', 1), 'outlet': f'Paper {i}', 'p': 1 - i / 40}
            for i, (a, b) in enumerate((w, x) for w in WORDS for x in ('',))][:15]
    return sat, real


def test_real_or_satire_is_the_same_all_day():
    sat, real = satire_pool()
    a = play.pick_real_or_satire(sat, real, '2026-10-28')
    assert a == play.pick_real_or_satire(sat, real, '2026-10-28')
    days = {json.dumps(play.pick_real_or_satire(sat, real, f'2026-10-{d:02d}')) for d in range(1, 15)}
    assert len(days) > 5  # the days differ


@pytest.mark.parametrize('day', [f'2026-11-{d:02d}' for d in range(1, 11)])
def test_real_or_satire_mixes_and_prefers_hard_ones(day):
    sat, real = satire_pool()
    picked = play.pick_real_or_satire(sat, real, day)
    kinds = [p['kind'] for p in picked]
    assert len(picked) == 5 and kinds.count('satire') in (2, 3)
    groups = {p['group'] for p in picked if p['kind'] == 'satire'}
    assert groups == {'left', 'right'}  # satire from both sides
    assert all(p['p'] <= 0.4 for p in picked if p['kind'] == 'satire')  # among the most real-looking
    assert all(p['p'] >= 0.75 for p in picked if p['kind'] == 'real')  # among the most satire-looking
    assert len({p['outlet'] for p in picked}) == 5


def lean_pool():
    out = []
    for n, s in enumerate(('left', 'center', 'right')):
        for o in range(5):
            for i in range(3):
                out.append({'title': WORDS[(n * 5 + o) % len(WORDS)].split()[i] + f' {s}{o}', 'outlet': f'{s}-{o}',
                            'side': s, 'guess': s, 'conf': 0.86 + i / 100})
    out.append({'title': 'unsure one', 'outlet': 'x', 'side': 'left', 'guess': 'left', 'conf': 0.6})
    out.append({'title': 'wrong one', 'outlet': 'y', 'side': 'left', 'guess': 'right', 'conf': 0.99})
    return out


@pytest.mark.parametrize('day', [f'2026-11-{d:02d}' for d in range(1, 8)])
def test_guess_the_lean_is_sure_mixed_and_steady(day):
    picked = play.pick_lean(lean_pool(), day)
    assert picked == play.pick_lean(lean_pool(), day)
    assert len(picked) == 5 and len({p['outlet'] for p in picked}) == 5
    assert all(p['conf'] >= 0.85 and p['guess'] == p['side'] for p in picked)
    sides = sorted(p['side'] for p in picked)
    assert {sides.count(s) for s in ('left', 'center', 'right')} == {1, 2}


def test_puzzles_keep_apart_from_each_other():
    sat = [{'title': 'Senator Smith eats the budget whole', 'outlet': 'A', 'group': 'left', 'p': 0.01},
           {'title': 'Senator Smith budget vote delayed again', 'outlet': 'B', 'group': 'right', 'p': 0.02},
           {'title': 'Cat elected mayor of quiet village', 'outlet': 'C', 'group': 'right', 'p': 0.03}]
    for d in range(1, 10):
        picked = play.pick_real_or_satire(sat, [], f'2026-12-{d:02d}', 3)
        titles = {p['title'] for p in picked}
        assert not {'Senator Smith eats the budget whole', 'Senator Smith budget vote delayed again'} <= titles


def test_two_papers_takes_the_furthest_pair_that_shares_words():
    def h(title, side, tilt):
        return {'title': title, 'outlet': f'{side}-{tilt}', 'side': side, 'tilt': tilt}
    stories = [{'id': 1, 'label': 'Judge rules on firing', 'outlets': 40, 'headlines': [
                   h('Judge rules DOJ unlawfully fired prosecutor', 'left', -0.6),
                   h('Rally in Georgia draws crowds', 'right', 0.95),  # nothing in common: skipped
                   h('Federal judge says DOJ fired Comey daughter unlawfully', 'right', 0.7),
                   h('Center take on the judge', 'center', 0.0)]},
               {'id': 2, 'label': 'Small story', 'outlets': 30, 'headlines': [
                   h('Budget passes Senate', 'left', -0.2), h('Senate budget passes', 'right', 0.2)]}]
    pair = play.best_pair(stories)
    assert pair['story'] == 1
    assert pair['left']['title'].startswith('Judge rules DOJ')
    assert pair['right']['title'].startswith('Federal judge')
    assert play.best_pair([{'id': 3, 'label': 'x', 'outlets': 5, 'headlines': [h('Only one side here', 'left', -1)]}]) is None
# </editor-fold>


# <editor-fold desc="scoring">
def test_score_counts_both_kinds_of_right_answer():
    kinds = ['satire', 'real', 'real', 'satire', 'real']
    s = play.score(kinds, ['satire', 'real', 'satire', 'real', 'real'])
    assert (s['satire_hits'], s['satire'], s['real_hits'], s['real'], s['right'], s['of']) == (1, 2, 2, 3, 3, 5)
    assert s['grid'] == '🟩🟩🟥🟥🟩'
    cry_wolf = play.score(kinds, ['satire'] * 5)  # calling everything satire
    trusting = play.score(kinds, ['real'] * 5)
    assert cry_wolf['satire_hits'] == 2 and cry_wolf['real_hits'] == 0 and cry_wolf['right'] == 2
    assert trusting['right'] == 3 and trusting['satire_hits'] == 0
    assert play.score(['left', 'right'], ['left', 'center'])['right'] == 1


@pytest.mark.skipif(not shutil.which('node'), reason='node not installed')
def test_the_pages_script_scores_like_python():
    with open(j2env.loader.get_source(j2env, 'play.html')[1], encoding='utf-8') as f:
        source = f.read()
    js = re.search(r'// score:start.*?\n(.*?)// score:end', source, re.S).group(1)
    cases = [(['satire', 'real', 'real', 'satire', 'real'], ['satire', 'real', 'satire', 'real', 'real']),
             (['satire', 'real'], ['satire', 'satire']), (['left', 'center', 'right'], ['left', 'right', 'right'])]
    script = js + f'\nconsole.log(JSON.stringify({json.dumps(cases)}.map(c => score(c[0], c[1]))));'
    out = json.loads(subprocess.run(['node', '-e', script], capture_output=True, text=True, check=True).stdout)
    assert out == [play.score(k, a) for k, a in cases]
# </editor-fold>


# <editor-fold desc="the page and its card">
GAMES = {'day': '2026-10-27',
         'satire': [{'title': 'Cat <elected> mayor', 'kind': 'satire', 'outlet': 'The Onion', 'link': 'https://o.example/1',
                     'group': 'left', 'bias': None, 'p': 0.02, 'when': 'Oct 27'},
                    {'title': 'Pumpkin carver hailed as Picasso', 'kind': 'real', 'outlet': 'Winnipeg Free Press',
                     'link': 'story-12.html', 'group': None, 'bias': None, 'p': 0.9, 'when': 'Oct 26'}],
         'lean': [{'title': 'Blakeman mocks Hochul', 'outlet': 'Fox News', 'side': 'right', 'bias': 2, 'conf': 0.99,
                   'link': 'https://f.example/2', 'url': 'https://f.example/2', 'lean_url': 'https://allsides.example',
                   'other': [{'title': 'Hochul hits back', 'outlet': 'CNN', 'side': 'left', 'bias': -1}]}],
         'pair': {'story': 991, 'label': 'Judge blocks new charges', 'outlets': 57, 'link': 'story-991.html', 'gap': 1.8,
                  'left': {'title': 'DOJ charges Comey a third time', 'outlet': 'HuffPost', 'side': 'left', 'bias': -2,
                           'tilt': -0.9, 'url': 'https://h.example'},
                  'right': {'title': 'DOJ hits Comey with new charges', 'outlet': 'Red State', 'side': 'right',
                            'bias': 2, 'tilt': 0.9, 'url': 'https://r.example'}}}


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'build', str(tmp_path / 'build'))
    monkeypatch.setattr(share_images, 'cache_dir', lambda: str(tmp_path / 'cache'))
    (tmp_path / 'build').mkdir()
    return tmp_path


def test_two_papers_card_is_1200_by_630(scratch):
    path = share_images.two_papers_card('Judge blocks new charges', GAMES['pair']['left'], GAMES['pair']['right'],
                                        'Oct 27')
    with Image.open(scratch / 'build' / path) as im:
        assert im.size == (1200, 630)


def test_page_renders_the_games(scratch, monkeypatch):
    monkeypatch.setitem(j2env.globals, 'icons', {})
    monkeypatch.setitem(j2env.globals, 'unrated', {'Winnipeg Free Press'})
    monkeypatch.setitem(j2env.globals, 'lean_estimates', {})
    ctx = page_play.context(GAMES)
    TemplateHandler('play.html').write(ctx)
    html = (scratch / 'build' / 'play.html').read_text(encoding='utf-8')
    for marker in ('{{', '{%', '#}'):
        assert marker not in html
    soup = BeautifulSoup(html, 'html.parser')
    key = json.loads(soup.select_one('#play-key').string)
    assert key['satire'] == ['satire', 'real'] and key['lean'] == ['right'] and key['url'].endswith('/play')
    assert 'Cat &lt;elected&gt; mayor' in html  # headlines are escaped
    assert len(soup.select('.play-round[data-game=satire] .play-card')) == 2
    assert all(r.has_attr('hidden') for r in soup.select('.play-reveal'))
    assert soup.select_one('meta[property="og:image"]')['content'].endswith('.png')
    assert 'papers-' in soup.select_one('meta[property="og:image"]')['content']
    assert 'AllSides' in soup.select_one('#guess-the-lean + .play-intro').text
    assert 'Hochul hits back' in html


def test_page_without_puzzles_says_so(scratch):
    TemplateHandler('play.html').write(page_play.context(page_play.EMPTY))
    soup = BeautifulSoup((scratch / 'build' / 'play.html').read_text(encoding='utf-8'), 'html.parser')
    assert len(soup.select('.stage-empty')) >= 3
    assert not soup.select('.play-card')
# </editor-fold>
