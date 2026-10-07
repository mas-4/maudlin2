"""scripts/maudlin_mcp.py: the read-only data server. Queries answer; writes can't happen, plain or hidden in a WITH."""
import importlib.util
import json
import os
import sqlite3

spec = importlib.util.spec_from_file_location('maudlin_mcp', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'maudlin_mcp.py'))
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def test_queries_answer_and_writes_cannot(tmp_path, monkeypatch):
    db = tmp_path / 'd.db'
    con = sqlite3.connect(db)
    con.execute('create table t (a text)')
    con.executemany('insert into t values (?)', [('x' * 1000,), ('y',)])
    con.commit()
    con.close()
    monkeypatch.setattr(server, 'DB', str(db))
    assert 't: 2 rows' in server.db_schema()
    out = json.loads(server.db_query('select a from t', limit=1))
    assert out['rows'][0][0].endswith('(1000 chars)') and 'more' in out
    assert server.db_query('delete from t').startswith('read-only')
    assert 'readonly' in server.db_query('with x as (select 1) delete from t')
    assert sqlite3.connect(db).execute('select count(*) from t').fetchone()[0] == 2


def test_changes_go_through_the_checker_marked_and_only_claudes_are_undone(tmp_path, monkeypatch):
    import threading
    from http.server import ThreadingHTTPServer

    from app.analysis import motif_index as mi
    spec2 = importlib.util.spec_from_file_location('validate', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'validate.py'))
    validate = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(validate)
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    for k, v in (('FOLDER', tmp_path), ('CURATION_LOG', tmp_path / 'log.jsonl'), ('UNDO', tmp_path / 'undo')):
        monkeypatch.setattr(validate, k, str(v))  # never the real log or undo folder
    mi.save({'next': 3, 'claims': {}, 'entries': {'M001': {'id': 'M001', 'name': 'Empty suit', 'claims': []},
                                                    'M002': {'id': 'M002', 'name': 'Rigged vote', 'claims': []}}})
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), validate.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    monkeypatch.setattr(server, 'CHECKER', f'http://127.0.0.1:{httpd.server_address[1]}')
    monkeypatch.setattr(server, '_V', validate)
    try:
        assert server.checker_action({'action': 'rename', 'id': 'M001', 'name': 'Hollow suit'}).startswith('done')
        assert mi.load()['entries']['M001']['name'] == 'Hollow suit'
        row = json.loads((tmp_path / 'log.jsonl').read_text().splitlines()[-1])
        assert row['by'] == 'claude' and 'by' not in row['action']
        assert server.checker_action({'action': 'parent', 'id': 'M001', 'parent': 'M404'}).startswith('refused')
        assert server.checker_undo().startswith('undid') and mi.load()['entries']['M001']['name'] == 'Empty suit'
        # the person's change on top: never undone by Claude
        server._post('/workbench', {'action': 'rename', 'id': 'M002', 'name': 'Stolen vote'})
        assert "person's" in server.checker_undo() and mi.load()['entries']['M002']['name'] == 'Stolen vote'
    finally:
        httpd.shutdown()


def test_undo_takes_back_a_proposal_decision_too(tmp_path, monkeypatch):
    """Undoing an approval reverts the change and reopens the proposal; a rejection is a step of its own (Oct 7: undo
    skipped rejections, and an undone approval stayed approved, so proposals vanished)"""
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    from app.analysis import motif_index as mi
    from app.analysis import motif_proposals as mp
    from app.utils.store import write_json
    spec2 = importlib.util.spec_from_file_location('validate', os.path.join(os.path.dirname(__file__), '..', 'scripts', 'validate.py'))
    validate = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(validate)
    monkeypatch.setattr(mi, 'INDEX', str(tmp_path / 'index.json'))
    monkeypatch.setattr(mp, 'PROPOSALS', str(tmp_path / 'proposals.json'))
    for k, v in (('FOLDER', tmp_path), ('CURATION_LOG', tmp_path / 'log.jsonl'), ('UNDO', tmp_path / 'undo')):
        monkeypatch.setattr(validate, k, str(v))
    mi.save({'next': 4, 'claims': {}, 'entries': {i: {'id': i, 'name': n, 'claims': []} for i, n in
                                                    (('M001', 'Empty suit'), ('M002', 'Rigged vote'), ('M003', 'Big lie'))}})
    store = {}
    mp.add(store, 'relate', {'a': 'M001', 'b': 'M002'}, 'cousins')
    mp.add(store, 'relate', {'a': 'M002', 'b': 'M003'}, 'cousins too')
    write_json(mp.PROPOSALS, store)
    good, bad = sorted(store, key=lambda i: store[i]['reason'])
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), validate.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{httpd.server_address[1]}'
    post = lambda path, body: urllib.request.urlopen(urllib.request.Request(url + path, json.dumps(body).encode(), {'Content-Type': 'application/json'})).read()  # noqa: E731
    try:
        post('/workbench', {'action': 'relate', 'a': 'M001', 'b': 'M002', 'proposal': good})
        post('/workbench', {'action': 'proposal_reject', 'proposal': bad})
        assert [p['id'] for p in mp.open_proposals()] == []
        assert 'reject a proposal' in post('/undo', {}).decode()  # the rejection: newest, undone first
        assert [p['id'] for p in mp.open_proposals()] == [bad]
        post('/undo', {})  # the approval: the link goes and the proposal is back
        assert mi.load().get('related', []) == [] and {p['id'] for p in mp.open_proposals()} == {good, bad}
    finally:
        httpd.shutdown()
