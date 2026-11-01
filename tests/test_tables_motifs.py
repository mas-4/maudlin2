"""The motifs group's tables in data.db (Nov 1): the proposals, the checker's undo stack, the watch list and the
reranker's teachings, through the code that reads and writes them, and the one-time import from the data folder."""
import json

import pytest

from app.analysis import motif_proposals as mp, reranker_teach as rt, watch_list as wl
from app.tables.motifs import CheckerUndo, MotifProposal, RerankerTeaching, WatchClaim, WatchUnfound
from scripts.json_import import motifs as importer
from tests.load import script
from tests.motifs_db import memory_db


@pytest.fixture
def db(monkeypatch):
    return memory_db(monkeypatch)


def proposal(i, **kw):
    return {'id': i, 'kind': 'relate', 'args': {'a': 'M001', 'b': 'M002'}, 'reason': 'cousins', 'model': 'm',
            'made': '2026-11-01T10:00:00', 'status': 'open', **kw}


def test_proposals_round_trip_with_their_nested_parts(db):
    store = {'p1': proposal('p1', judge={'p': 0.5, 'score': 5.0, 'reason': '', 'model': 'nimble'}, fit=0.7),
             'p2': proposal('p2', status='rejected', decided='2026-11-01T11:00:00', why='not cousins',
                            final={'action': 'relate'})}
    mp.replace_all(store)
    assert mp.load() == store
    with db() as s:
        assert s.get(MotifProposal, 'p1').fit == 0.7 and json.loads(s.get(MotifProposal, 'p2').final) == {'action': 'relate'}
    assert json.loads(mp.export_text()) == store  # a checkpoint's text


def test_a_runs_save_keeps_the_persons_decisions_and_adds_its_own(db):
    mp.replace_all({'p1': proposal('p1')})
    run = mp.load()  # a run reads, then the person decides in the checker meanwhile
    mp.decide('p1', 'approved', 'yes, cousins')
    run['p1']['fit'] = 0.9
    mp.add(run, 'relate', {'a': 'M002', 'b': 'M003'}, 'more cousins')
    mp.save(run)
    got = mp.load()
    assert got['p1']['status'] == 'approved' and got['p1']['why'] == 'yes, cousins' and got['p1']['fit'] == 0.9
    assert len(got) == 2


def test_decide_critique_and_reopen(db):
    mp.replace_all({'p1': proposal('p1')})
    mp.decide('p1', 'approved', final={'action': 'relate', 'a': 'M001', 'b': 'M009'})
    assert mp.load()['p1']['final']['b'] == 'M009'
    assert mp.critique('p1', ' wrong   pair ')['why'] == 'wrong pair'
    assert mp.reopen(['p1', 'nope']) == ['p1']
    p = mp.load()['p1']
    assert p['status'] == 'open' and 'decided' not in p and 'final' not in p and p['why'] == 'wrong pair'
    with pytest.raises(ValueError):
        mp.decide('nope', 'approved')


def test_the_undo_stack_keeps_the_newest_and_steps_back(db, monkeypatch):
    from app.analysis import entities
    validate = script('validate')
    monkeypatch.setattr(validate, 'UNDO_KEEP', 3)
    monkeypatch.setattr(validate, 'log_curation', lambda *a, **k: None)
    for n in range(5):  # five steps on the names page
        before = validate.state(entities.ALIASES)
        entities.save_aliases({'aliases': {'the donald': f'Donald Trump {n}'}, 'not_same': []})
        validate.push_undo(entities.ALIASES, before, f'step {n}', proposals=['p1'] if n == 4 else None, log=n or None)
    with db() as s:
        assert s.query(CheckerUndo).count() == 3  # the newest UNDO_KEEP
    _, snap = validate.last_undo()
    assert snap['what'] == 'step 4' and snap['proposals'] == ['p1'] and snap['log'] == 4
    assert validate.undo() == 'step 4'
    assert entities.load_aliases()['aliases']['the donald'] == 'Donald Trump 3'
    assert validate.last_undo()[1]['what'] == 'step 3'


def test_the_watch_list_round_trips(db):
    store = {'claims': {'k1': {'key': 'k1', 'claim': 'A thing happened', 'source': 'narrative', 'ref': 'r',
                               'date': '2026-10-10', 'story': 294, 'story_tie': 'same event', 'plain': True,
                               'why': 'watched motif', 'since': '2026-10-13', 'refiled': '2026-10-29T03:31:27'},
                        'k2': {'key': 'k2', 'claim': 'Another', 'source': 'shows', 'date': '2026-10-07',
                               'plain': False, 'since': '2026-10-13'}},
             'unfound': {'k3': '2026-11-01'}}
    wl.save(store)
    assert wl.load() == store
    wl.save({'claims': {}})
    assert wl.load() == {'claims': {}}


def test_the_latest_teaching_decides_the_reranker(db, monkeypatch, tmp_path):
    assert rt.meta() == {}
    with db() as s:
        s.add_all([RerankerTeaching(at='2026-10-01T00:00:00', examples=1, decisions=2, kept='taught'),
                   RerankerTeaching(at='2026-10-08T00:00:00', examples=3, decisions=4, kept='base')])
        s.commit()
    assert rt.meta() == {'at': '2026-10-08T00:00:00', 'examples': 3, 'decisions': 4, 'kept': 'base'}
    monkeypatch.setattr(rt, 'TAUGHT', str(tmp_path / 'taught.pt'))
    assert rt.tag() == 'base'
    (tmp_path / 'taught.pt').write_bytes(b'x')
    assert rt.tag() == '2026-10-08T00:00:00'


def test_the_import_fills_the_tables_and_moves_the_caches(db, tmp_path):
    data, cache = tmp_path / 'data', tmp_path / 'data' / 'cache'
    (data / 'motifs' / 'reranker').mkdir(parents=True)
    (data / 'validation' / 'undo').mkdir(parents=True)
    (data / 'validation' / 'motifs').mkdir()
    (data / 'validation' / 'motifs' / 'claims.json').write_text('{}')
    proposals = {'p1': proposal('p1', judge={'p': 0.4}), 'p2': proposal('p2', status='none', kind='link_ok')}
    (data / 'motif_proposals.json').write_text(json.dumps(proposals))
    for stamp, what in (('20261101-085223-280842', 'first'), ('20261101-092849-568634', 'second')):
        (data / 'validation' / 'undo' / f'{stamp}.json').write_text(json.dumps(
            {'path': '/x/motif_index.json', 'before': 'txn:4', 'after_sha': 'abc', 'after': 'txn:5', 'what': what,
             'at': stamp, 'proposals': ['p1'], 'log': 7}))
    (data / 'motifs' / 'watch_list.json').write_text(json.dumps(
        {'claims': {'k1': {'key': 'k1', 'claim': 'c', 'source': 's', 'date': '2026-10-10', 'plain': True, 'why': None,
                           'since': '2026-10-13'}}, 'unfound': {'k2': '2026-11-01'}}))
    (data / 'motifs' / 'reranker' / 'taught.json').write_text(json.dumps({'at': '2026-10-08T19:56:08', 'examples': 2319,
                                                                          'decisions': 753}))
    for rel in ('motifs/claim_shapes.json', 'motifs/reranker/held_out.json', 'motifs/motif_space.json'):
        (data / rel).write_text('{"x": 1}')
    with db() as s:
        counts = importer.run(s, str(data), str(cache))
        s.commit()
    assert counts == {'motif_proposal': 2, 'checker_undo': 2, 'watch_claim': 1, 'watch_unfound': 1,
                      'reranker_teaching': 1, 'caches moved': 3}
    assert mp.load() == proposals
    with db() as s:
        undo = s.query(CheckerUndo).order_by(CheckerUndo.id).all()
        assert [u.what for u in undo] == ['first', 'second'] and undo[1].after == 'txn:5' and undo[1].log == 7
        assert s.get(WatchClaim, 'k1').plain is True and s.get(WatchUnfound, 'k2').day == '2026-11-01'
    assert rt.meta()['decisions'] == 753
    assert json.loads((cache / 'motifs' / 'reranker' / 'held_out.json').read_text()) == {'x': 1}
    assert not (data / 'motifs' / 'claim_shapes.json').exists() and (cache / 'motifs' / 'claim_shapes.json').exists()
    assert (data / 'motif_proposals.json').exists()  # a source file is never deleted
    assert (data / 'validation' / 'motifs' / 'claims.json').exists()  # read by nothing: left alone


def test_the_import_of_an_empty_folder_counts_nothing(db, tmp_path):
    with db() as s:
        counts = importer.run(s, str(tmp_path), str(tmp_path / 'cache'))
    assert set(counts.values()) == {0}
