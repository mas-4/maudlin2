"""The experiments' own data folder (Oct 15; the person: "you can copy the current data from the prod stuff but it
should run separate please"). Until now experiments ran production's code on production's data folder and fenced
themselves off file by file (each its own sandbox() of redirected paths); every file one forgot leaked into production:
the test suite's fake filings in the shortlist log (624 rows), Rip Van Winkle's 687 sandbox filings on the 🧠 Live
page and in the shortlist log. Now each queued step runs with MAUDLIN_DATA pointing here (app/utils/config.py), so
whatever it writes stays here.

    ~/maudlin-lab/data     a copy of production's data folder, refreshed before each step that starts fresh: files
                           copied when production's are newer or a different size, databases by SQLite's backup (a
                           plain copy of a database being written can come out torn); never written back
    shared, linked         what belongs to the experiments themselves, kept where production's checker reads it:
                           motifs/experiments (their state, results, queue), archives (the archive experiments'
                           database), papers
    left out               production's coordination and logs: the GPU lease, the worker's heartbeat, the GPU log, the
                           app log (an experiment's own go here)

    lab_data.py refresh    bring the copy up to date (the queue does this itself)"""
import os
import shutil
import sqlite3
import sys
import time

PROD = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data'))
LAB = os.path.expanduser('~/maudlin-lab/data')
SHARED = ('motifs/experiments', 'archives', 'papers')
SKIP = {'app.log', 'gpu_log.csv', 'gpu_lease.json', 'gpu_lease.json.lock', 'worker.json'}
SKIP_ENDS = ('.tmp', '-journal', '-wal', '-shm', '.lock')
DATABASES = ('.db', '.sqlite')


def _link_shared(prod: str = PROD, lab: str = LAB):
    for rel in SHARED:
        src, dst = os.path.join(prod, rel), os.path.join(lab, rel)
        if not os.path.exists(src) or os.path.islink(dst):
            continue
        if os.path.exists(dst):
            raise RuntimeError(f'{dst} is a real folder in the lab: it should link to production\'s')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.symlink(src, dst)


def _backup(src: str, dst: str):
    """A database copied whole and consistent, through SQLite, into a temporary file first"""
    tmp = dst + '.copying'
    source = sqlite3.connect(f'file:{src}?mode=ro', uri=True, timeout=60)
    target = sqlite3.connect(tmp)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    # the old copy's write-ahead log and index go with it: left beside the new file, SQLite reads them as the new
    # file's and the copy comes out malformed (Oct 18: the lab's narrative embeddings, 3.7 GB, copied in again while a
    # step that had it open crashed and restarted, broke Baron Munchausen's report three times)
    for side in ('-wal', '-shm'):
        if os.path.exists(dst + side):
            os.remove(dst + side)
    os.replace(tmp, dst)
    shutil.copystat(src, dst)


def refresh(prod: str = PROD, lab: str = LAB) -> dict:
    """The lab brought up to date with production: {'copied', 'databases', 'seconds'}"""
    t0 = time.time()
    os.makedirs(lab, exist_ok=True)
    _link_shared(prod, lab)
    shared = {os.path.join(prod, rel) for rel in SHARED}
    copied = databases = 0
    for folder, dirs, files in os.walk(prod):
        dirs[:] = [d for d in dirs if os.path.join(folder, d) not in shared]
        out = os.path.join(lab, os.path.relpath(folder, prod))
        os.makedirs(out, exist_ok=True)
        for name in files:
            if name in SKIP or name.endswith(SKIP_ENDS) or name.endswith('.copying'):
                continue
            src, dst = os.path.join(folder, name), os.path.join(out, name)
            try:
                st = os.stat(src)
                if os.path.exists(dst):
                    have = os.stat(dst)
                    if have.st_size == st.st_size and have.st_mtime >= st.st_mtime:
                        continue
                if name.endswith(DATABASES):
                    _backup(src, dst)
                    databases += 1
                else:
                    shutil.copy2(src, dst)
                    copied += 1
            except (OSError, sqlite3.Error) as e:  # a file gone or busy mid-walk: the next refresh gets it
                print(f'lab_data: {src}: {e}', flush=True)
    return {'copied': copied, 'databases': databases, 'seconds': round(time.time() - t0, 1)}


if __name__ == '__main__':
    if sys.argv[1:] == ['refresh']:
        print(refresh(), flush=True)
    else:
        print(__doc__)
