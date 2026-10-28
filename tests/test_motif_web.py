"""The motif index across the site (app/analysis/motif_web.py): who told a story from which side, each show's
repertoire and neighbours, the motifs told about a name, how long an answer took, the motifs' words in headlines,
the cloud of stories told, and a saga's telling day by day."""
from datetime import datetime, timedelta

from app.analysis import motif_web as w
from app.site.page_saga import drift


def row(motif, name, claim, kind='shows', teller='Show A', side='left', date='2026-10-20', story=None, genre='Plots'):
    return {'motif': motif, 'name': name, 'genre': genre, 'claim': claim, 'key': claim.lower(), 'kind': kind,
            'teller': teller, 'side': side, 'date': date, 'story': story, 'url': ''}


def test_a_story_is_told_by_side_with_its_answer():
    rows = [row('M1', 'Lawfare', 'The DOJ targets critics.', teller='Mockler', side='left', story=5),
            row('M1', 'Lawfare', 'Democrats want lawfare.', teller='Megyn', side='right', story=5),
            row('M2', 'No one is above the law', 'A judge signed the warrant.', teller='Bongino', side='right', story=5),
            row('M1', 'Lawfare', 'Omar is persecuted.', kind='posts', teller='people online', side=None, story=5),
            row('M3', 'Elsewhere', 'Not this story.', story=9)]
    index = {'related': [['M1', 'M2']], 'related_notes': {'M1|M2': 'No one is above the law answers Lawfare'}}
    entries = {'M1': {'name': 'Lawfare'}, 'M2': {'name': 'No one is above the law'}, 'M3': {'name': 'Elsewhere'}}
    told = w.by_story(rows, index, entries)[5]
    assert [m['id'] for m in told] == ['M1', 'M2']  # the most tellers first
    assert told[0]['sides']['left'] == ['Mockler'] and told[0]['sides']['right'] == ['Megyn'] and told[0]['sides']['posts'] == 1
    assert told[0]['answers'] == [{'id': 'M2', 'name': 'No one is above the law', 'note': 'No one is above the law answers Lawfare'}]


def test_a_show_telling_carries_who_said_it_the_hosts_own_voice_first(monkeypatch):
    from app.analysis import show_claims
    eps = {'u1': {'show': 'Left Show', 'lean': 'left', 'date': '2026-10-20'},
           'u2': {'show': 'Left Show', 'lean': 'left', 'date': '2026-10-21'},
           'u3': {'show': 'Right Show', 'lean': 'right', 'date': '2026-10-21'}}
    group = {'claim': 'Acton is an impostor.',
             'told': [{'show': 'Left Show', 'url': 'u1', 'speaker': 'clip', 'claim': 'Acton is a fraud.'},
                      {'show': 'Left Show', 'url': 'u2', 'speaker': 'host', 'claim': 'Acton is a fake.'},
                      {'show': 'Right Show', 'url': 'u3', 'speaker': 'clip', 'claim': 'Acton is an impostor.'}]}
    monkeypatch.setattr(show_claims, 'load', lambda: eps)
    monkeypatch.setattr(show_claims, 'kept_retold', lambda: [group])
    told = w.show_tellers()[w.mi.key('Acton is a fraud.')]
    assert {t['show']: t['speaker'] for t in told} == {'Left Show': 'host', 'Right Show': 'clip'}


def test_sides_are_counted_on_hosts_and_guests_once_per_motif_per_episode():
    rows = [dict(row('M1', 'Lawfare', 'a', teller='A'), speaker='host', url='ep1'),
            dict(row('M1', 'Lawfare', 'b', teller='A'), speaker='guest', url='ep1'),  # the same episode again
            dict(row('M1', 'Lawfare', 'c', teller='A'), speaker='host', url='ep2'),
            dict(row('M1', 'Lawfare', 'd', teller='B'), speaker='clip', url='ep3'),
            dict(row('M1', 'Lawfare', 'e', teller='C'), speaker='caller', url='ep4'),
            dict(row('M1', 'Lawfare', 'f', teller='D'), speaker='', url='ep5'),
            row('M1', 'Lawfare', 'g', kind='posts', teller='people online', side=None)]
    assert [r['claim'] for r in w.spoken(rows)] == ['a', 'c']


def test_a_shows_signature_is_what_it_tells_more_than_the_others_and_its_neighbours_tell_alike():
    rows = []
    for n in range(10):
        rows.append(row('M1', 'Lawfare', f'a{n}', teller='A', side='right'))
        rows.append(row('M1', 'Lawfare', f'b{n}', teller='B', side='left'))
        rows.append(row('M9', 'Ballot dump', f'c{n}', teller='C', side='center'))
    rows += [row('M2', 'Sharia takeover', f'a2{n}', teller='A', side='right') for n in range(4)]
    shows = w.shows(rows)
    assert shows['A']['signature'][0][1] == 'Sharia takeover'  # A's own, the others never tell it
    assert shows['A']['neighbours'][0][0] == 'B'  # A tells like B (both Lawfare), not like C, whatever their leans


def test_a_name_gets_the_motifs_told_about_it_by_its_name_or_an_alias():
    rows = [row('M1', 'The impostor', 'Ilhan Omar married her brother.'),
            row('M2', 'Lawfare', 'Omar is being persecuted by the DOJ.'),
            row('M3', 'Senile leader', 'Trump fell asleep again.')]
    told = w.people(rows, ['Ilhan Omar', 'Donald Trump'], {'omar': 'Ilhan Omar', 'trump': 'Donald Trump'})
    assert {m['name'] for m in told['Ilhan Omar']} == {'The impostor', 'Lawfare'}
    assert [m['name'] for m in told['Donald Trump']] == ['Senile leader']


def test_an_answers_lag_is_the_days_between_first_tellings():
    rows = [row('M1', 'Ballot dump', 'x', date='2026-10-17'), row('M2', 'Red mirage', 'y', date='2026-10-26')]
    index = {'related': [['M1', 'M2']], 'related_notes': {'M1|M2': 'Red mirage answers Ballot dump'}}
    entries = {'M1': {'name': 'Ballot dump'}, 'M2': {'name': 'Red mirage'}}
    lag = w.answer_lag(rows, index, entries)
    assert lag['M1'][0]['days'] == 9 and lag['M2'][0]['days'] == -9


def test_a_motifs_words_are_found_whole_by_group_and_plots_left_out():
    entries = {'M1': {'id': 'M1', 'name': 'Rigged election', 'facets': {'genre': 'Theories'}, 'groups': [], 'claims': []},
               'M2': {'id': 'M2', 'name': 'Found dead', 'facets': {'genre': 'Plots'}, 'groups': [], 'claims': []},
               'M3': {'id': 'M3', 'name': 'Inflation', 'facets': {'genre': 'Theories'}, 'groups': [], 'claims': []}}
    lex = w.lexicon(entries)
    assert set(lex) == {'rigged election'}  # Plots say what a report says plainly; one word is a topic
    found = w.words_in([('Trump calls it a RIGGED ELECTION', 'right'), ('Rigged election claims debunked', 'left'),
                        ('Unrigged elections', 'center')], lex)
    assert found == [{'phrase': 'rigged election', 'id': 'M1', 'name': 'Rigged election', 'n': 2,
                      'by': {'right': 1, 'left': 1}}]


def test_the_cloud_of_stories_told_sizes_by_tellers_and_colors_by_side():
    today = datetime.now().date().isoformat()
    old = (datetime.now() - timedelta(days=30)).date().isoformat()
    rows = [row('M1', 'Lawfare', 'a', teller='A', side='left', date=today),
            row('M1', 'Lawfare', 'b', teller='B', side='right', date=today),
            row('M2', 'Sharia takeover', 'c', teller='C', side='right', date=today),
            row('M3', 'Old news', 'd', date=old)]
    cloud = {c['text']: c for c in w.cloud(rows)}
    assert set(cloud) == {'Lawfare', 'Sharia takeover'}
    assert cloud['Lawfare']['color'] == 'balanced' and cloud['Sharia takeover']['color'] == '#e0102e'
    assert cloud['Lawfare']['outlets'] == 2 and cloud['Lawfare']['url'].startswith('motif-m')


def test_told_against_checked_finds_the_unchecked():
    rows = [row('M1', 'Voter fraud', f'c{n}', kind='posts', teller='people online', side=None) for n in range(5)]
    rows += [row('M2', 'Rigged election', 'x', kind='check', teller='Snopes', side=None)]
    out = w.checked_vs_told(rows)
    assert [m['name'] for m in out['unchecked']] == ['Voter fraud'] and out['checked'][0]['name'] == 'Rigged election'


def test_a_sagas_drift_marks_the_motifs_new_that_day():
    rows = [row('M1', 'Straight news', 'a', date='2026-10-20', story=1),
            row('M2', 'Lawfare', 'b', date='2026-10-21', story=2),
            row('M1', 'Straight news', 'c', date='2026-10-21', story=2),
            row('M3', 'Other saga', 'd', date='2026-10-21', story=7)]
    days = drift(rows, {1, 2})
    assert [d['day'] for d in days] == ['2026-10-21', '2026-10-20']
    assert {m['name']: m['new'] for m in days[0]['motifs']} == {'Lawfare': True, 'Straight news': False}
