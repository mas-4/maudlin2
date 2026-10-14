"""app/deck.py: what the Stream Deck's keys show and do (no device)"""
import json
import time

from app import deck


def index():
    return {'entries': {
        'M9': {'id': 'M9', 'name': 'Not my president', 'first_seen': '2026-10-11',
               'claims': [{'claim': 'a', 'date': '2026-10-11'}]},
        'M10': {'id': 'M10', 'name': 'Cheap labor', 'first_seen': '2026-10-11', 'claims': []},
        'M2': {'id': 'M2', 'name': 'Manchurian candidate', 'first_seen': '2026-10-01',
               'claims': [{'claim': c, 'date': '2026-10-11'} for c in 'bcd'] + [{'claim': 'e', 'date': '2026-10-10'}]},
        'M3': {'id': 'M3', 'name': 'Gone', 'first_seen': '2026-10-11', 'merged_into': 'M2', 'claims': []}}}


def test_newborn_and_most_retold_motifs_today():
    assert [e['id'] for e in deck.newborn(index(), '2026-10-11')] == ['M10', 'M9']  # newest first, merged ones out
    assert [(e['id'], n) for e, n in deck.retold(index(), '2026-10-11')] == [('M2', 3), ('M9', 1)]


def test_every_key_draws_with_or_without_data():
    for state in ({}, {'news': {'kind': 'big', 'share': 61}, 'to_judge': 177,
                       'retold': deck.retold(index(), '2026-10-11'), 'mood': [('fear', 0.35)],
                       'gpu': ('worker', 80.0), 'party_until': time.time() + 10}):
        faces = deck.faces(state, (80, 80), time.time())
        assert len(faces) == 6 and all(f.size == (80, 80) for f in faces)


def test_the_unicorn_key_asks_the_lights_for_the_rainbow(monkeypatch, tmp_path):
    from app import lights
    monkeypatch.setattr(deck.Config, 'data', str(tmp_path))
    state = {}
    deck.press(state, 5)
    until = json.loads((tmp_path / lights.PARTY).read_text())['until']
    assert until == state['party_until'] and 25 < until - time.time() <= deck.PARTY_SECONDS


def test_the_claims_to_judge_key_counts_claims_with_an_unchecked_filing():
    ix = index()
    ix['entries']['M2']['claims'][0]['checked'] = 'yes'
    ix['entries']['M9']['claims'].append({'claim': 'c'})  # c is in two motifs: one claim
    assert deck.to_judge(ix) == 4  # a, c, d, e (b was checked)
    assert deck.shame(0) == (50, 170, 90) and deck.shame(150) == deck.shame(400) == (220, 30, 40)
