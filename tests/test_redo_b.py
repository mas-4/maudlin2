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


def test_group_titles_joins_wordings_of_one_story_but_not_on_common_words():
    from app.site import page_tv
    titles = ['Federal Reserve meeting begins', 'Federal Reserve begins two-day meeting on interest rates',
              'Milwaukee Brewers win Game 3 against Tampa Bay', 'Brewers lead Tampa Bay Rays 3-0 in World Series',
              'Democrats hold advantage in midterm election polls', 'Voter turnout in midterm election grows',
              'Midterm election ad spending', 'Midterm election early ballots', 'Pope Leo cleared to travel']
    others = [f'Unrelated story number{i} about topic{i}' for i in range(12)]  # enough titles for a word to be common
    groups = page_tv.group_titles([{'text': t} for t in titles + others])
    joined = sorted(sorted(i['text'] for i in g) for g in groups if len(g) > 1)
    assert joined == sorted([sorted(titles[:2]), sorted(titles[2:4])])  # midterm and election are in too many to join on


def test_tv_skipped_lists_front_page_leaders_with_little_time_on_air():
    from datetime import datetime as dt
    from app.site import page_tv
    caps = [{'at': dt(2026, 10, 5, 18), 'channel': 'CNNW', 'seconds': 60, 'text': 'X', 'story': 1, 'rank': 1, 'label': 'a'},
            {'at': dt(2026, 10, 5, 18), 'channel': 'FOXNEWSW', 'seconds': 900, 'text': 'Y', 'story': 2, 'rank': 2,
             'label': 'b'}]
    led = {1: {'id': 1, 'label': 'Quiet one', 'hours': 6, 'best': 1}, 2: {'id': 2, 'label': 'Loud one', 'hours': 9, 'best': 1},
           3: {'id': 3, 'label': 'Never aired', 'hours': 4, 'best': 3}, 4: {'id': 4, 'label': 'Brief', 'hours': 1, 'best': 9}}
    rows = page_tv.skipped(caps, led, dt(2026, 10, 5))
    assert [(r['name'], r['figure'], r['mark']) for r in rows] == [('Quiet one', '6 h · 60 s', 'CNN'),
                                                                   ('Never aired', '4 h · none', '📵')]
    assert 'Not on any channel' in rows[1]['tip']


def test_tv_swimlane_puts_each_channel_hour_in_its_lane_and_flips_on_a_phone():
    from datetime import datetime as dt
    from app.site import page_tv
    caps = [{'at': dt(2026, 10, 5, 18, 5), 'channel': 'CNNW', 'seconds': 120, 'text': 'A', 'story': 7, 'rank': 2,
             'label': 'Story', 'program': 'News'},
            {'at': dt(2026, 10, 5, 19, 5), 'channel': 'BBCNEWS', 'seconds': 30, 'text': 'B', 'program': 'World'}]
    lane = page_tv.swimlane(page_tv.hours(caps))
    assert [x['mark'] for x in lane['lanes']] == ['CNN', 'BBC'] and lane['cols'] == 2
    cnn, bbc = lane['cells']
    assert (cnn['row'], cnn['col'], cnn['flip'], cnn['rank']) == (2, 2, 3, 2)  # oldest left; at the bottom on a phone
    assert (bbc['row'], bbc['col'], bbc['flip'], bbc['rank']) == (3, 3, 2, None)
    assert cnn['head'] == '📺 CNN, Mon Oct 5, 2 PM ET · News' and '#2 on the front pages, as “Story”' in cnn['tip']
    assert [h['label'] for h in lane['hours']] == ['Mon 2 PM', '3 PM']


def cast(source, published, items, front=()):
    return {'source': source, 'show': {'nprnewsnow': 'NPR News Now', 'abcupdate': 'ABC News Update'}[source],
            'published': published, 'items': items,
            'front_top': [{'id': i, 'label': f'story {i}', 'outlets': 50 - i} for i in front]}


def test_radio_pair_counts_newscasts_off_the_front_pages_and_front_page_leaders_skipped():
    from app.site import page_radio
    casts = [cast('nprnewsnow', f'2026-10-05T{h:02d}:09', [{'title': 'Brewers win World Series game'},
                                                           {'title': 'Story one', 'story': 1, 'front_rank': 1,
                                                            'story_label': 'story 1'}], front=(1, 2, 3))
             for h in range(10, 14)]
    casts.append(cast('abcupdate', '2026-10-05T13:30', [{'title': 'Milwaukee Brewers win World Series'}], front=(1, 2, 3)))
    off = page_radio.off_front(casts)
    assert [(r['name'], r['figure'], r['mark']) for r in off] == [('Milwaukee Brewers win World Series', '5 newscasts', 'NPR')]
    assert 'NPR News Now 4 · ABC News Update 1' in off[0]['tip']
    skipped = page_radio.skipped(casts, now={2})
    # stories 2 and 3 led for 4 hours and no newscast said them; story 1 was in every newscast
    assert [(r['name'], r['figure'], r['mark'], r['href']) for r in skipped] == [
        ('story 2', '4 h · 0 newscasts', '📵', 'index.html#s-2'), ('story 3', '4 h · 0 newscasts', '📵', None)]
    store = dict(enumerate(casts))
    npr = page_radio.stickers(store)[0]
    assert (npr['show'], npr['casts'], npr['bars'][0]['pct'], npr['bars'][2]['pct']) == ('NPR News Now', 4, 0, 50)
    lane = page_radio.swimlane(page_radio.hours(store))
    assert [x['name'] for x in lane['lanes']] == ['NPR News Now', 'ABC News Update', 'The front pages']
    assert len(lane['cells']) == 4 + 1 + 4  # NPR's four newscasts, ABC's one, the front pages' four hours


def clip(text, titles, kind='clip'):
    return {'kind': kind, 'text': text, 'airings': [{'source': f's{i}', 'title': t} for i, t in enumerate(titles)]}


def test_replay_says_who_is_speaking_where_the_words_or_the_titles_do():
    from app.site import page_replay as pr
    assert pr.about(clip("My name is Donna Arthur, and I'm Amy Acton's mother. I love her.", [])) == \
        "🗣️ Speaking, in their own words: Donna Arthur, “I'm Amy Acton's mother”"
    assert pr.about(clip('Hi, everyone. Ilhan here. Thank you.', [])) == \
        '🗣️ Speaking, in their own words: Ilhan (“Ilhan here”)'
    assert pr.about(clip("I'm Sherrod Brown and I approve this message.", [], 'campaign')).startswith(
        '🗳️ The candidate speaking: Sherrod Brown')
    assert pr.about(clip('Vote early. Paid for by Ohio Forward Action. Not authorized by any candidate.', [],
                         'campaign')) == '🗳️ Paid for by Ohio Forward Action, it says'
    # names the clip says that the episodes' titles have too: the full name over its parts, common words never
    text = ('Well, the Senate race. Vivek Ramaswamy said it again in Ohio, and Right now the Republicans are worried. '
            'Obama never did.')
    titles = ["Ramaswamy's October surprise", 'Vivek Ramaswamy doubles down', 'Ohio Senate Republicans Panic',
              'Republicans In Ohio, Right Now']
    assert pr.about(clip(text, titles)) == ('📝 Named in the clip and in the titles of the episodes that played it: '
                                            'Ramaswamy (2 of 4), Ohio (2 of 4)')  # never Senate, Right, Republicans
    titles.append('Vivek Ramaswamy, again')
    line = pr.about(clip(text, titles))  # the full name, once two titles have it, over its part
    assert 'Vivek Ramaswamy (2 of 5)' in line and 'Ramaswamy (3' not in line
    assert pr.about(clip('So he said it. Then he left.', ['So It Goes', 'Then And Now'])) is None


def test_replay_explains_crossover_where_its_lane_and_count_appear():
    from bs4 import BeautifulSoup
    from app.site import page_replay as pr
    airings = [{'source': 'pod_rogan', 'show': 'Joe Rogan', 'group': 'crossover', 'title': 'Ep', 'url': 'https://x/1',
                'published': '2026-10-20T18:00:00', 'at': None}]
    svg = BeautifulSoup(pr.strip(airings), 'html.parser')
    label = next(t for t in svg.select('text.sc-label') if 'crossover' in t.get_text())
    assert label.title.get_text() == pr.CROSSOVER and 'Theo Von' in pr.CROSSOVER


def test_beyond_subjects_diverge_left_and_right_with_the_rest_across_the_middle(monkeypatch, tmp_path):
    from bs4 import BeautifulSoup
    from app.site import page_beyond as pb
    from app.utils.config import Config
    items = [{'group': 'left', 'subjects': ['congress', 'sports']}, {'group': 'left', 'subjects': ['congress']},
             {'group': 'right', 'subjects': ['congress']}, {'group': 'crossover', 'subjects': ['congress']},
             {'subjects': ['congress']}]  # an investigation: no group
    congress, sports = pb.subject_strip(items)
    assert (congress['left'], congress['elsewhere'], congress['right'], congress['n']) == (2, 2, 1, 5)
    assert congress['w_left'] + congress['w_mid'] == 50  # the widest side reaches the end of its half
    assert sports['w_right'] == 0 and sports['tip'] == '🫏 1 from left-leaning shows'
    assert '⚖️ 2 from center and crossover shows, investigations' in congress['tip']

    monkeypatch.setattr(pb.sidefeeds, 'recent', lambda **k: [
        {'title': 'Ep. 9', 'url': 'https://pod.example/9', 'summary': '', 'source': 'Show A', 'kind': 'podcast',
         'group': 'left', 'published': '2026-10-04T12:00:00+00:00'}])
    monkeypatch.setattr(pb.investigations, 'recent', lambda **k: [])
    monkeypatch.setattr(pb.subjects, 'tag', lambda items: {'https://pod.example/9': ['Congress and <legislation>']})
    monkeypatch.setattr(Config, 'build', str(tmp_path))
    pb.BeyondPage().generate()
    page = BeautifulSoup((tmp_path / 'beyond.html').read_text(), 'html.parser')
    row = page.select_one('.bypg-row')  # a button that filters the cards, as the subject buttons did
    assert row['data-subject'] == 'Congress and <legislation>' and row['aria-pressed'] == 'false'
    assert row.select_one('.bypg-left') and not row.select_one('.bypg-right')
    assert page.select_one('.narrative[data-subjects="|Congress and <legislation>|"]')
    assert not page.select('.narrative-tools button[data-subject]:not(.bypg-row)')  # no wall of subject buttons
    assert not page.select('.source-list [title]')
