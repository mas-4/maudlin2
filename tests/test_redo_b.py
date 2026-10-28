"""The site redo's group B (Oct 28): show pages, On TV, On the radio, Beyond the front pages and the Replay as ranked
strips in answering pairs (app/site/boards.py), the detail in hover cards."""
from app.site import boards, page_show


def telling(show, motif, n=1, genre='Plots', name=None):
    return [{'kind': 'shows', 'teller': show, 'motif': motif, 'name': name or f'motif {motif}', 'genre': genre,
             'key': f'{show}{motif}{i}'} for i in range(n)]


def web_rows():
    rows = []
    rows += telling('Alpha', 'M1', 6, 'Theories') + telling('Alpha', 'M2', 4) + telling('Alpha', 'M3', 2)
    rows += telling('Beta', 'M2', 5) + telling('Beta', 'M4', 5, 'Arguments') + telling('Beta', 'M3', 1)
    rows += telling('Gamma', 'M4', 6, 'Arguments') + telling('Gamma', 'M5', 3, None) + telling('Gamma', 'M2', 1)
    rows += [{'kind': 'posts', 'teller': 'people online', 'motif': 'M9', 'name': 'online only', 'genre': 'Plots',
              'key': 'p1'}]
    return rows


def test_times_more_compares_shares_and_never_divides_by_nothing():
    assert page_show.times_more(5, 100, 9, 900) == (5 / 100) / (10 / 900)
    assert page_show.times_more(2, 10, 0, 1000) == (2 / 10) / (1 / 1000)
    assert page_show.times(12.4) == '×12' and page_show.times(2.25) == '×2.2'


def test_tells_more_shows_signature_motifs_by_how_many_times_more_often():
    t = page_show.tellings(web_rows())
    sh = {'signature': [('M1', 'motif M1', 3.0), ('M3', 'motif M3', 1.0), ('M2', 'motif M2', 0.1)]}
    rows = page_show.tells_more('Alpha', sh, t)
    # M1 only here, then M3 (2 of 12 against 1 of 21); M2 (4 of 12 against 6 of 21) is under MORE_LEAST
    assert [r['name'] for r in rows] == ['motif M1', 'motif M3']
    assert rows[0]['figure'] == 'only here' and rows[0]['bar'] == 100
    assert rows[0]['ink'] == boards.GENRE_INK['Theories'] and rows[0]['mark_label'] == 'Theories'
    assert 'Alpha: 6 of its 12 tellings' in rows[0]['tip'] and 'none of the other 2 shows' in rows[0]['tip']
    assert rows[1]['figure'].startswith('×')


def test_never_tells_ranks_the_others_motifs_by_how_many_shows_told_them():
    t = page_show.tellings(web_rows())
    rows = page_show.never_tells('Alpha', t, {'Beta': 'right', 'Gamma': 'left'})
    assert [r['name'] for r in rows] == ['motif M4', 'motif M5']  # never M9, told online, not on a show
    assert rows[0]['figure'] == '2 shows' and '🫏 1 leans left' in rows[0]['tip'] and '🐘 1 leans right' in rows[0]['tip']
    assert rows[1]['ink'] == boards.UNCOLORED and rows[1]['mark_label'] == 'No genre yet'


def test_alike_pairs_most_and_least_by_cosine_colored_by_lean():
    t = page_show.tellings(web_rows())
    likes = page_show.likeness(t, ['Alpha', 'Beta', 'Gamma'])
    assert likes['Alpha']['Beta'] == likes['Beta']['Alpha'] > likes['Alpha']['Gamma']
    rows = page_show.alike_rows('Alpha', sorted(likes['Alpha'].items(), key=lambda i: -i[1]), t,
                                {'Beta': 'right', 'Gamma': None}, {'Beta'})
    assert rows[0]['name'] == 'Beta' and rows[0]['ink'] == boards.LEAN_INK['right'] and rows[0]['mark'] == '🐘'
    assert rows[0]['href'] == page_show.show_href('Beta') and rows[1]['href'] is None  # Gamma has no page
    assert rows[1]['mark_label'] == 'not grouped by lean'
    assert '2 motifs in common: motif M2, motif M3' in rows[0]['tip']


def test_show_boards_come_in_pairs_with_the_repertoire_counting_on():
    rows = web_rows()
    for i in range(30):
        rows += telling('Alpha', f'X{i:02d}', 1)
    t = page_show.tellings(rows)
    from collections import Counter
    c = Counter(r['motif'] for r in rows if r.get('teller') == 'Alpha')
    sh = {'signature': [('M1', 'motif M1', 3.0)], 'motifs': [(m, f'motif {m}', n) for m, n in c.most_common()]}
    likes = page_show.likeness(t, ['Alpha', 'Beta', 'Gamma'])
    out = page_show.show_boards('Alpha', sh, t, {'Beta': 'right', 'Gamma': 'left'}, likes)
    assert [b['key'] for b in out['signature']] == ['more', 'never']
    assert [b['key'] for b in out['alike']] == ['alike', 'unalike']
    assert [len(b['rows']) for b in out['repertoire']] == [page_show.FIRST, 33 - page_show.FIRST]
    assert out['repertoire'][0]['rows'][0]['figure'] == '×6'
    assert out['alike'][1]['rows'] == []  # two other shows: too few for a least-alike list beside the most alike
    assert {k['name'] for k in out['lean_key']} == {'leans left', 'leans right'}
    assert out['mix'][0]['genre'] == 'Plots' and round(sum(g['share'] for g in out['mix'])) == 100
