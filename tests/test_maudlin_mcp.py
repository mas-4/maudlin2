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
