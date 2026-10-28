"""The aisle (app/site/page_aisle.py): the motif map as the stories each side tells, left to right."""
from app.site import page_aisle


def row(motif, side, teller, kind='shows', speaker='host'):
    return {'motif': motif, 'name': motif.title(), 'genre': 'Plots', 'claim': f'{motif} {teller}', 'key': f'{motif}{teller}',
            'kind': kind, 'teller': teller, 'side': side, 'date': '2026-10-26', 'story': None, 'url': '',
            'speaker': speaker if kind == 'shows' else None}


def test_a_clip_a_show_played_doesnt_place_a_motif_on_its_side():
    web = {'rows': [row('impostor', 'left', 'A', speaker='clip'), row('impostor', 'left', 'B', speaker='clip'),
                    row('impostor', 'right', 'C'), row('impostor', 'right', 'D', speaker='guest'),
                    row('played', 'left', 'A', speaker='clip')],
           'entries': {m: {'name': m.title(), 'note': ''} for m in ('impostor', 'played')}}
    dots = {d['id']: d for d in page_aisle.place(web)}
    assert dots['impostor']['left'] == 0 and dots['impostor']['right'] == 2 and dots['impostor']['lean'] == 0.5
    assert dots['impostor']['told'] == 4  # the height still counts every telling
    assert 'played' not in dots  # only ever played in a clip: no side to put it on


def test_a_motif_sits_by_which_sides_shows_told_it_and_few_shows_pull_it_to_the_middle():
    web = {'rows': [row('lawfare', 'left', 'A'), row('lawfare', 'right', 'B'),
                    row('sharia', 'right', 'B'), row('sharia', 'right', 'C'), row('sharia', 'right', 'D'),
                    row('one', 'left', 'A'), row('online', None, 'people online', kind='posts')],
           'entries': {m: {'name': m.title(), 'note': ''} for m in ('lawfare', 'sharia', 'one', 'online')}}
    dots = {d['id']: d for d in page_aisle.place(web)}
    assert set(dots) == {'lawfare', 'sharia', 'one'}  # told only online: not on the aisle
    assert dots['lawfare']['lean'] == 0
    assert dots['sharia']['lean'] == 0.6 and dots['one']['lean'] == -1 / 3  # pulled to the middle when few told it


def test_the_divide_chart_draws_a_dot_a_week_with_partial_weeks_hollow():
    week = {'jsd': 0.5, 'floor': 0.3, 'floor_p05': 0.25, 'floor_p95': 0.36, 'index': 0.2, 'left': 50, 'right': 60,
            'left_shows': 5, 'right_shows': 6}
    weeks = [dict(week, week='2026-10-13', first='2026-10-13', last='2026-10-19', partial=True),
             dict(week, week='2026-10-20', first='2026-10-20', last='2026-10-26', partial=False, index=0.23)]
    svg = str(page_aisle.divide_chart(weeks))
    assert svg.count('class="divide-dot') == 2 and svg.count('divide-partial') == 1
    assert 'Oct 20–26: 0.23' in svg and '>0.23</text>' in svg and 'class="divide-band"' in svg
    assert page_aisle.divide_chart([]) is None and page_aisle.day_span('2026-09-29', '2026-10-05') == 'Sep 29–Oct 5'


def test_the_aisle_draws_every_dot_and_joins_answers():
    one = {'lean': 0.5, 'told': 30, 'left': 2, 'right': 7, 'center': 1}
    two = {'lean': -0.4, 'told': 20, 'left': 5, 'right': 3, 'center': 1}
    dots = [{'id': 'M1', 'name': 'Voter fraud', 'genre': 'Theories', **one, 'spots': {'all': one, 'week': one},
             'trend': 'rising', 'href': 'motif-m1.html'},
            {'id': 'M2', 'name': 'Voter suppression', 'genre': 'Plots', **two, 'spots': {'all': two}, 'trend': 'steady',
             'href': 'motif-m2.html'}]
    svg = str(page_aisle.draw(dots, [('M1', 'M2', 'Voter suppression answers Voter fraud')]))
    assert svg.count('class="aisle-dot ') == 2 and 'class="aisle-arc"' in svg and '>Voter fraud</text>' in svg
    assert svg.count('class="aisle-ring"') == 1 and svg.count('data-week=') == 1  # only M1 rises, and was told this week


def test_a_motif_rises_when_told_twice_as_often_this_week():
    from datetime import date
    rows = [dict(row('lawfare', 'left', f'S{n}'), date=f'2026-10-{d:02d}') for n, d in enumerate([25, 26, 27, 26])]
    rows += [dict(row('fading', 'right', f'T{n}'), date='2026-10-15') for n in range(4)]
    rows += [dict(row('fading', 'right', 'T9'), date='2026-10-25')]
    web = {'rows': rows, 'entries': {'lawfare': {'name': 'Lawfare'}, 'fading': {'name': 'Fading'}}}
    dots = {d['id']: d for d in page_aisle.place(web, today=date(2026, 10, 27))}
    assert dots['lawfare']['trend'] == 'rising' and dots['fading']['trend'] == 'fading'
    assert dots['lawfare']['daily'][-3:] == [1, 2, 1] and 'days3' in dots['lawfare']['spots']


def crossover(motif, teller, source):
    """A telling on a crossover show: no side on the aisle, its group from app/sidefeeds.py"""
    return dict(row(motif, None, teller), show_source=source)


def test_only_in_the_center_means_center_shows_and_no_other_shows_at_all():
    web = {'rows': [row('french', 'center', 'Daily'), row('french', 'center', 'Up First'),  # two center shows: in
                    row('once', 'center', 'Daily'),  # one show's habit, not the center's
                    row('clipped', 'center', 'Daily'), row('clipped', 'center', 'Up First'),
                    row('clipped', 'left', 'Pod', speaker='clip'),  # a left show played it: heard on the left
                    row('crossed', 'center', 'Daily'), row('crossed', 'center', 'Up First'),
                    crossover('crossed', 'Rogan', 'pod_rogan'),
                    row('both', 'left', 'Pod'), row('both', 'right', 'Bongino'), row('both', 'center', 'Daily'),
                    crossover('rogan', 'Rogan', 'pod_rogan'), crossover('rogan', 'Dillon', 'pod_dillon')],
           'entries': {m: {'name': m.title(), 'note': ''} for m in ('french', 'once', 'clipped', 'crossed', 'both', 'rogan')}}
    center = page_aisle.only_in(web, 'center')
    assert [d['id'] for d in center] == ['french'] and center[0]['shows'] == ['Daily', 'Up First']
    # crossover is its own group: a motif only crossover shows told is theirs (and never placed on the aisle)
    assert [d['id'] for d in page_aisle.only_in(web, 'crossover')] == ['rogan']
    assert 'rogan' not in {d['id'] for d in page_aisle.place(web)}


def test_the_lists_color_each_motif_by_its_genre_with_its_emoji():
    items = [{'name': 'Voter fraud', 'href': 'm1.html', 'genre': 'Theories', 'week': 9},
             {'name': 'Sports', 'href': 'm2.html', 'genre': 'Perennials', 'week': 3}]
    rows = page_aisle.strip(items, lambda d: d['week'], lambda d: str(d['week']), lambda d: d['genre'])
    assert rows[0]['ink'] == page_aisle.GENRE_INK['Theories'] and rows[0]['emoji'] == '🕵️' and rows[0]['bar'] == 100
    assert rows[1]['ink'] == page_aisle.UNCOLORED and rows[1]['emoji'] == '🌻' and rows[1]['bar'] == 33
    inks = list(page_aisle.GENRE_INK.values())
    assert len(set(inks)) == len(inks) and not set(inks) & set(page_aisle.LEAN_INK.values())  # never a lean color
    assert list(page_aisle.GENRE_INK) == [g for g in page_aisle.GENRE_EMOJI if g in page_aisle.GENRE_INK]  # fixed order


def test_the_aisle_page_renders_its_lists_as_ranked_strips(tmp_path, monkeypatch):
    from bs4 import BeautifulSoup

    from app.site.common import j2env
    from app.utils.config import Config
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    monkeypatch.setitem(j2env.globals, 'icons', {})
    rows = [row('french', 'center', 'Daily'), row('french', 'center', 'Up First'),
            dict(row('lawfare', 'left', 'Pod'), genre='Theories'), dict(row('lawfare', 'right', 'Bongino'), genre='Theories'),
            row('senile', 'left', 'Pod'), row('senile', 'left', 'Majority')]
    entries = {m: {'name': m.title(), 'note': ''} for m in ('french', 'lawfare', 'senile')}
    monkeypatch.setattr(page_aisle, 'shared', lambda: {'web': {'rows': rows, 'entries': entries, 'answers': {}}})
    page_aisle.AislePage().generate()
    soup = BeautifulSoup((tmp_path / 'motif-map.html').read_text(encoding='utf-8'), 'html.parser')
    lists = soup.select_one('.aisle-lists')
    assert not lists.select('.stage-notes') and not lists.select('[title]')  # no dashed boxes, no tooltips
    boards = {b.h3.get_text(strip=True): b for b in lists.select('.aisle-board')}
    assert set(boards) >= {'🫏 Mostly left', '🐘 Mostly right', '⚖️ Told on both sides', '🎯 Only in the center'}
    center = boards['🎯 Only in the center'].select('.aisle-row')
    assert [a.select_one('.aisle-row-name').text for a in center] == ['French']
    assert 'Daily, Up First' in center[0]['data-tip'] and '--genre: #a0522d' in center[0]['style']  # Plots' brown
    both = boards['⚖️ Told on both sides'].select_one('.aisle-row')
    assert both.select_one('[role=img]')['aria-label'] == 'Theories' and '#8a5cff' in both['style']
    assert [k.b.text for k in lists.select('.aisle-key-item')][:2] == ['Archetypes', 'Plots']
    assert '🦗' in boards['🐘 Mostly right'].text  # an empty list says so
