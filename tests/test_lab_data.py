"""scripts/experiments/lab_data.py: the experiments' own copy of the data (Oct 15). Files and databases copied, the
experiments' own folders linked, production's coordination files left out, and nothing copied twice."""
import os
import sqlite3
import sys

sys.path.insert(0, 'scripts/experiments')
import lab_data  # noqa: E402


def test_the_lab_is_a_copy_with_the_experiments_folders_shared(tmp_path):
    prod, lab = tmp_path / 'prod', tmp_path / 'lab'
    (prod / 'motifs' / 'experiments').mkdir(parents=True)
    (prod / 'motif_index.json').write_text('{"entries": {}}')
    (prod / 'motifs' / 'shortlist_log.jsonl').write_text('{}\n')
    (prod / 'motifs' / 'experiments' / 'results.log').write_text('kept where it is\n')
    (prod / 'worker.json').write_text('{}')  # production's coordination: not copied
    con = sqlite3.connect(prod / 'data.db')
    con.execute('create table headline (title text)')
    con.execute("insert into headline values ('a')")
    con.commit()
    con.close()
    out = lab_data.refresh(str(prod), str(lab))
    assert out['copied'] == 2 and out['databases'] == 1
    assert (lab / 'motif_index.json').read_text() == '{"entries": {}}'
    assert sqlite3.connect(lab / 'data.db').execute('select title from headline').fetchall() == [('a',)]
    assert os.path.islink(lab / 'motifs' / 'experiments') and (lab / 'motifs' / 'experiments' / 'results.log').exists()
    assert not (lab / 'worker.json').exists()
    (lab / 'motif_index.json').write_text('{"entries": {"M1": {}}}')  # an experiment writes its copy...
    assert (prod / 'motif_index.json').read_text() == '{"entries": {}}'  # ...production's is untouched
    assert lab_data.refresh(str(prod), str(lab))['copied'] == 1  # the next fresh step starts from production's again
    assert (lab / 'motif_index.json').read_text() == '{"entries": {}}'
    assert lab_data.refresh(str(prod), str(lab)) | {'seconds': 0} == {'copied': 0, 'databases': 0, 'seconds': 0}


def test_a_database_copied_again_leaves_no_old_write_ahead_log_beside_it(tmp_path):
    """Oct 18: the old copy's -wal and -shm, left beside a new copy, made it malformed"""
    prod, lab = tmp_path / 'prod', tmp_path / 'lab'
    prod.mkdir()
    con = sqlite3.connect(prod / 'cache.sqlite')
    con.execute('create table vec (k text)')
    con.commit()
    con.close()
    lab_data.refresh(str(prod), str(lab))
    (lab / 'cache.sqlite-wal').write_bytes(b'stale frames of the old copy')
    (lab / 'cache.sqlite-shm').write_bytes(b'stale index')
    con = sqlite3.connect(prod / 'cache.sqlite')
    con.execute("insert into vec values ('new')")
    con.commit()
    con.close()
    os.utime(prod / 'cache.sqlite', (os.path.getmtime(lab / 'cache.sqlite') + 10,) * 2)
    assert lab_data.refresh(str(prod), str(lab))['databases'] == 1
    assert not (lab / 'cache.sqlite-wal').exists() and not (lab / 'cache.sqlite-shm').exists()
    assert sqlite3.connect(lab / 'cache.sqlite').execute('pragma quick_check').fetchone() == ('ok',)
