"""A data folder to try the checker's writes in, without touching the person's (Oct 21, for the React port).

Everything is linked from the real data folder for reading, except what the checker writes, which is copied: the
motif index, the proposals, the names, the curation log and undo stack (validation/), Pandora's tellings, and the
experiments' verdicts. The curation database gets the person's decisions only, not the old index versions. Then run a second checker on it:

    .venv/bin/python scripts/checker/ui/sandbox.py /path/to/sandbox
    MAUDLIN_DATA=/path/to/sandbox MAUDLIN_TRACE=off .venv/bin/python scripts/validate.py --port 8799

and the React app's dev server (`npm run dev`, which sends the API to 8799) or http://127.0.0.1:8799/ui/. Never test
writes on the live checker (8766): its undo stack is the person's."""
import os
import shutil
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
REAL = os.path.realpath(os.path.join(ROOT, 'data'))
# Copied, not linked: what the checker's writes change (paths relative to the data folder)
COPY = ['motif_index.sqlite', 'motif_index.json', 'motif_proposals.json', 'motif_proposals_runs.json', 'entity_aliases.json',
        'validation', 'motifs/experiments/f10_pandora.json', 'motifs/experiments/f22_psyche.json']
SKIP = {'curation.sqlite', 'app.log', 'gpu_lease.json', 'worker.json'}  # made apart (_curation), or the real processes' own


def build(dest: str):
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)
    copied = {c.split('/')[0] for c in COPY}
    for name in os.listdir(REAL):
        if name in SKIP or name.endswith(('.lock', '-wal', '-shm', '.tmp')):
            continue
        src, dst = os.path.join(REAL, name), os.path.join(dest, name)
        if name in copied and name not in COPY:  # a folder with some files copied: link the rest one by one
            _mirror(src, dst, [c.split('/', 1)[1] for c in COPY if c.startswith(name + '/')])
        elif name in COPY:
            _copy(src, dst)
        else:
            os.symlink(src, dst)
    _curation(os.path.join(REAL, 'curation.sqlite'), os.path.join(dest, 'curation.sqlite'))
    print(f'sandbox at {dest}: {len(os.listdir(dest))} entries')


def _curation(src: str, dst: str):
    """The curation database with the person's decisions only (the confidence model reads them), not its 1.4 GB of
    old index versions"""
    if not os.path.exists(src):
        return
    sys.path.insert(0, ROOT)
    from app.analysis import curation_db
    con = sqlite3.connect(dst)
    con.executescript(curation_db.SCHEMA)
    con.execute('ATTACH DATABASE ? AS real', (src,))
    con.execute('INSERT INTO curation SELECT * FROM real.curation')
    con.commit()
    con.close()


def _mirror(src: str, dst: str, copy: list[str]):
    os.makedirs(dst)
    heads = {c.split('/')[0] for c in copy}
    for name in os.listdir(src):
        s, d = os.path.join(src, name), os.path.join(dst, name)
        if name in heads and name not in copy:
            _mirror(s, d, [c.split('/', 1)[1] for c in copy if c.startswith(name + '/')])
        elif name in copy:
            _copy(s, d)
        else:
            os.symlink(s, d)


def _copy(src: str, dst: str):
    if os.path.isdir(src):
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns('undo'))
    elif src.endswith('.sqlite'):  # a database: whole, through SQLite
        a, b = sqlite3.connect(src), sqlite3.connect(dst)
        a.backup(b)
        b.close(), a.close()
    elif os.path.exists(src):
        shutil.copy2(src, dst)


if __name__ == '__main__':
    build(sys.argv[1])
