"""The aisle (app/site/page_aisle.py): the motif map as the stories each side tells, left to right."""
from app.site import page_aisle


def row(motif, side, teller, kind='shows'):
    return {'motif': motif, 'name': motif.title(), 'genre': 'Plots', 'claim': f'{motif} {teller}', 'key': f'{motif}{teller}',
            'kind': kind, 'teller': teller, 'side': side, 'date': '2026-10-26', 'story': None, 'url': ''}


def test_a_motif_sits_by_which_sides_shows_told_it_and_few_shows_pull_it_to_the_middle():
    web = {'rows': [row('lawfare', 'left', 'A'), row('lawfare', 'right', 'B'),
                    row('sharia', 'right', 'B'), row('sharia', 'right', 'C'), row('sharia', 'right', 'D'),
                    row('one', 'left', 'A'), row('online', None, 'people online', kind='posts')],
           'entries': {m: {'name': m.title(), 'note': ''} for m in ('lawfare', 'sharia', 'one', 'online')}}
    dots = {d['id']: d for d in page_aisle.place(web)}
    assert set(dots) == {'lawfare', 'sharia', 'one'}  # told only online: not on the aisle
    assert dots['lawfare']['lean'] == 0
    assert dots['sharia']['lean'] == 0.6 and dots['one']['lean'] == -1 / 3  # pulled to the middle when few told it


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
