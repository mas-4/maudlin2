"""app/analysis/motif_db.py: the motif index in SQLite (Oct 21), read back exactly as saved, saved by the rows that
changed, taken back to any earlier save, and moved in from its JSON file without losing anything."""
import json
import sqlite3

import pytest

from app.analysis import motif_db, motif_index as mi


def sample() -> dict:
    claim = lambda t, **kw: {'claim': t, 'source': 'narrative', **kw}  # noqa: E731
    return {'next': 4, 'entries': {
        'M001': {'id': 'M001', 'name': 'Empty suit', 'curated': True, 'facets': {'genre': 'Archetypes'},
                 'claims': [claim('a', fit=0.91), claim('b — “quoted”', story=7)]},
        'M002': {'id': 'M002', 'name': 'Rigged votes', 'claims': []},
        'M003': {'id': 'M003', 'name': 'Old', 'merged_into': 'M001', 'claims': []}},
        'claims': {mi.key('a'): ['M001'], mi.key('gone'): []},
        'not_same': [['M001', 'M002']], 'related': [], 'corrections': {'b': 'b — “quoted”'},
        'groups': {'G01': {'name': 'Leaders', 'members': ['M001']}}, 'held': {}}


def canon(index: dict) -> str:
    return motif_db.canonical(index)


def test_an_index_reads_back_as_it_was_saved(tmp_path):
    path = str(tmp_path / 'index.sqlite')
    assert motif_db.read(path) == {'next': 1, 'entries': {}, 'claims': {}} and not (tmp_path / 'index.sqlite').exists()
    index = sample()
    assert motif_db.write(path, index) == 1
    back = motif_db.read(path)
    assert canon(back) == canon(index)
    assert list(back['entries']) == ['M001', 'M002', 'M003']  # the motifs' order kept
    assert back['related'] == [] and back['held'] == {}  # empty parts kept as what they were
    con = sqlite3.connect(path)  # and it can be read by hand
    assert con.execute("SELECT name FROM motifs WHERE merged_into IS NULL ORDER BY n").fetchall() == [('Empty suit',), ('Rigged votes',)]
    assert con.execute("SELECT motif FROM filings WHERE claim_key = ?", (mi.key('a'),)).fetchall() == [('M001',)]


def test_a_save_writes_and_logs_only_what_changed(tmp_path):
    path = str(tmp_path / 'index.sqlite')
    index = sample()
    motif_db.write(path, index)
    assert motif_db.write(path, index) == 1  # nothing changed: no new save
    index['entries']['M002']['claims'].append({'claim': 'c', 'source': 'shows'})
    index['claims'][mi.key('c')] = ['M002']
    assert motif_db.write(path, index) == 2
    con = sqlite3.connect(path)
    assert sorted(con.execute('SELECT tbl, old IS NULL FROM changes WHERE txn = 2')) == [('filings', 1), ('parts', 1)]


def test_any_earlier_save_can_be_gone_back_to(tmp_path):
    path = str(tmp_path / 'index.sqlite')
    index = sample()
    motif_db.write(path, index)
    first = canon(motif_db.read(path))
    index['entries']['M001']['name'] = 'Empty suits'
    del index['entries']['M001']['claims'][0]
    index['groups']['G02'] = {'name': 'New'}
    index['not_same'].append(['M002', 'M003'])
    motif_db.write(path, index)
    assert canon(motif_db.state_at(path, 1)) == first
    assert motif_db.revert(path, 1) == 3  # a save of its own...
    assert canon(motif_db.read(path)) == first
    assert canon(motif_db.state_at(path, 2)) == canon(index)  # ...so the going back can itself be taken back


def test_the_json_index_moves_in_whole(tmp_path, monkeypatch):
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'motif_index.sqlite'))
    (tmp_path / 'motif_index.json').write_text(json.dumps(sample()))
    assert mi._json_mode() and canon(mi.load()) == canon(sample())  # before the move: the JSON file, as before
    got = mi.migrate()
    assert got['motifs'] == 3 and got['filings'] == 2
    assert not (tmp_path / 'motif_index.json').exists() and not mi._json_mode()
    assert canon(mi.load()) == canon(sample())
    with pytest.raises(ValueError):
        mi.migrate()  # once only
    index = mi.load()
    index['entries']['M002']['name'] = 'Rigged count'
    mi.save(index)
    assert mi.version() == 2 and mi.load()['entries']['M002']['name'] == 'Rigged count'  # the move was save 1


def test_a_snapshot_is_read_once_a_save(tmp_path, monkeypatch):
    """mi.snapshot(): the checker's views share one parse of the index until the next save (Oct 22)"""
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.sqlite'))
    claim = {'claim': 'a', 'source': 'narrative'}
    mi.save({'next': 2, 'claims': {mi.key('a'): ['M001']}, 'entries': {'M001': {'id': 'M001', 'name': 'Empty suit', 'claims': [claim]}}})
    first = mi.snapshot()
    assert mi.snapshot() is first  # no save between: the same parse
    index = mi.load()
    assert index is not first  # load() is still a copy of one's own
    index['entries']['M001']['name'] = 'Empty suits'
    mi.save(index)
    assert mi.snapshot()['entries']['M001']['name'] == 'Empty suits'  # a save: read again
    assert first['entries']['M001']['name'] == 'Empty suit'


def test_the_curation_log_is_parsed_again_only_when_it_changes(tmp_path, monkeypatch):
    from app.analysis import curation_db
    monkeypatch.setattr(curation_db, 'DB', str(tmp_path / 'curation.sqlite'))
    with curation_db.connect() as con:
        for n in range(4):
            con.execute('INSERT INTO curation (at, page, by, action) VALUES (?, ?, ?, ?)', (f'2026-10-22T0{n}', 'p', None, json.dumps({'action': 'note', 'n': n})))
    assert [r['action']['n'] for r in curation_db.actions()] == [0, 1, 2, 3]
    with curation_db.connect() as con:  # a go-back: the same number of rows taken back, but other ones
        con.execute('UPDATE curation SET reverted = 1 WHERE id = 1')
    assert [r['action']['n'] for r in curation_db.actions()] == [1, 2, 3]
    with curation_db.connect() as con:
        con.execute('UPDATE curation SET reverted = 0')
        con.execute('UPDATE curation SET reverted = 1 WHERE id = 2')
    assert [r['action']['n'] for r in curation_db.actions()] == [0, 2, 3]
    assert [r['action']['n'] for r in curation_db.actions(include_reverted=True)] == [0, 1, 2, 3]
    with curation_db.connect() as con:
        con.execute('INSERT INTO curation (at, page, by, action) VALUES (?, ?, ?, ?)', ('2026-10-22T09', 'p', None, json.dumps({'action': 'note', 'n': 4})))
    assert [r['action']['n'] for r in curation_db.actions()] == [0, 2, 3, 4]


def test_a_claim_filed_again_by_hand_gets_back_where_it_came_from(monkeypatch, tmp_path):
    """Out of every motif a claim keeps no row; filed again by hand with no source, it lost its posts (Oct 24)"""
    path = str(tmp_path / 'index.sqlite')
    monkeypatch.setattr(mi, 'INDEX', path)
    index = sample()
    index['entries']['M001']['claims'][0].update(source='Snopes', ref='https://x')
    motif_db.write(path, index)
    mi.unfile('a', 'M001')
    assert not any(c['claim'] == 'a' for c in mi.load()['entries']['M001']['claims'])
    mi.file_by_hand({'claim': 'a', 'source': '', 'ref': ''}, 'M002')
    got = next(c for c in mi.load()['entries']['M002']['claims'] if c['claim'] == 'a')
    assert (got['source'], got['ref']) == ('Snopes', 'https://x')
    assert motif_db.last_origin(path, {mi.key('never filed')}) == {}
