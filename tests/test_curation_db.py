"""app/analysis/curation_db.py and the checker's checkpoints: every save of the motif index is logged; a state saved by
name can be gone back to, saving what was there first; the changes taken back stay in the log, marked, and the models
stop learning from them."""
import json

from app.analysis import curation_db, filing_confidence as fc, motif_index as mi, motif_proposals as mp
from tests.load import script

validate = script('validate')


def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(curation_db, 'DB', str(tmp_path / 'curation.sqlite'))
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(mp, 'PROPOSALS', str(tmp_path / 'proposals.json'))
    monkeypatch.setattr(validate, 'CURATION_LOG', str(tmp_path / 'curation_log.jsonl'))
    monkeypatch.setattr(validate, 'UNDO', str(tmp_path / 'undo'))
    monkeypatch.setattr(fc, 'CURATION_LOG', validate.CURATION_LOG)
    claim = lambda t: {'claim': t, 'source': 'narrative'}  # noqa: E731
    mi.save({'next': 3, 'claims': {mi.key('a'): ['M001']}, 'entries': {
        'M001': {'id': 'M001', 'name': 'Empty suit', 'claims': [claim('a'), claim('b')]},
        'M002': {'id': 'M002', 'name': 'Rigged votes', 'claims': [claim('c')]}}})
    (tmp_path / 'proposals.json').write_text(json.dumps({'p1': {'id': 'p1', 'status': 'open'}}))


def test_every_save_is_kept_once_as_the_rows_it_changed(tmp_path, monkeypatch):
    """Since Oct 21 the index is a database: a save logs the rows it changed, not a copy of the whole index"""
    import sqlite3
    setup(tmp_path, monkeypatch)
    first = mi.version()
    index = mi.load()
    mi.save(index)  # the same state: nothing kept again
    assert mi.version() == first
    index['entries']['M001']['name'] = 'Empty suits'
    mi.save(index)
    assert mi.version() == first + 1
    con = sqlite3.connect(mi.INDEX)
    changed = con.execute('SELECT tbl, key, old, new FROM changes WHERE txn = ?', (first + 1,)).fetchall()
    assert [(t, k) for t, k, _o, _n in changed] == [('motifs', 'M001')]
    assert '"Empty suit"' in changed[0][2] and '"Empty suits"' in changed[0][3]
    with curation_db.connect() as con:
        assert con.execute('SELECT COUNT(*) FROM versions').fetchone()[0] == 0  # no whole copies any more


def test_going_back_to_a_saved_state(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    saved = validate.save_checkpoint('before a big sweep')
    # changes after it, through the checker (logged)
    validate.workbench_action({'action': 'check', 'claim': 'a', 'id': 'M001', 'answer': 'no'})
    validate.log_curation('motif workbench', {'action': 'check', 'claim': 'a', 'id': 'M001', 'answer': 'no'}, {})
    (tmp_path / 'proposals.json').write_text(json.dumps({'p1': {'id': 'p1', 'status': 'approved'}}))
    assert 'a' not in [c['claim'] for c in mi.load()['entries']['M001']['claims']]
    assert fc.decisions(validate.CURATION_LOG) == {(mi.key('a'), 'M001'): False}
    assert curation_db.checkpoints()[0]['changes_since'] == 1
    done = validate.go_back(saved['id'])
    assert done['reverted'] == 1
    assert 'a' in [c['claim'] for c in mi.load()['entries']['M001']['claims']]  # the motif index as it was
    assert json.loads((tmp_path / 'proposals.json').read_text())['p1']['status'] == 'open'  # and the proposals
    assert fc.decisions(validate.CURATION_LOG) == {}  # the decision taken back isn't learned from
    assert len(curation_db.actions(include_reverted=True)) == 2  # but it's kept, marked (and the going back logged)
    # what was there before going back was saved, so going back can itself be undone
    first = next(c for c in curation_db.checkpoints() if c['kind'] == 'before going back')
    validate.go_back(first['id'])
    assert 'a' not in [c['claim'] for c in mi.load()['entries']['M001']['claims']]
    assert fc.decisions(validate.CURATION_LOG) == {(mi.key('a'), 'M001'): False}  # learned from again


def test_a_second_look_keeps_or_takes_out_a_confirmed_filing(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    index = mi.load()
    for c in index['entries']['M001']['claims']:
        c.update(checked='yes', fit=0.1 if c['claim'] == 'a' else 0.25 if c['claim'] == 'b' else 0.9)
    index['entries']['M001']['done'] = [mi.key('a'), mi.key('b')]
    mi.save(index)
    assert [r['claim'] for r in validate.second_look()] == ['a', 'b']  # the least likely first, only those under SECOND_LINE (0.3)
    mi.check('a', 'M001', 'yes')  # still fits: off the list
    assert [r['claim'] for r in validate.second_look()] == ['b']
    mi.check('b', 'M001', 'no')  # taken out
    assert validate.second_look() == []
