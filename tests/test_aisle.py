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
    dots = [{'id': 'M1', 'name': 'Voter fraud', 'genre': 'Theories', 'lean': 0.5, 'told': 30, 'left': 2, 'right': 7,
             'center': 1, 'href': 'motif-m1.html'},
            {'id': 'M2', 'name': 'Voter suppression', 'genre': 'Plots', 'lean': -0.4, 'told': 20, 'left': 5, 'right': 3,
             'center': 1, 'href': 'motif-m2.html'}]
    svg = str(page_aisle.draw(dots, [('M1', 'M2', 'Voter suppression answers Voter fraud')]))
    assert svg.count('class="aisle-dot"') == 2 and 'class="aisle-arc"' in svg and '>Voter fraud</text>' in svg
