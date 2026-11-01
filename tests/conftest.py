import os
import tempfile

# Before any app module sets up its logger: test runs (the pre-commit hook included) must not write into the real
# log, which lives in the data folder prod shares
os.environ['MAUDLIN_LOG_FILE'] = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-log-'), 'app.log')

# The database too (Nov 1): each run works on a copy of data.db, brought up to the newest migration, never the real
# one. Until then tests opened production's (the worktree's data folder is production's), so the suite failed until
# the hourly run had migrated it, and anything a test wrote landed there. On btrfs the copy is a reflink: instant.
_REAL_DATA = os.environ.get('MAUDLIN_DATA') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                            'data')


def _copy_database() -> str:
    import atexit
    import shutil
    import subprocess
    # Beside the repo, on the data's own disk, so the copy can be a reflink (/tmp is another filesystem, where each of
    # the 12 workers would copy the whole 600 MB); removed when the run ends
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.test-db')
    os.makedirs(base, exist_ok=True)
    folder = tempfile.mkdtemp(prefix='run-', dir=base)
    atexit.register(shutil.rmtree, folder, True)
    for suffix in ('', '-wal'):  # the WAL holds what isn't checkpointed into the file yet
        src = os.path.join(_REAL_DATA, 'data.db' + suffix)
        if os.path.exists(src):
            dst = os.path.join(folder, 'data.db' + suffix)
            if subprocess.run(['cp', '--reflink=auto', src, dst]).returncode:
                shutil.copyfile(src, dst)
    return folder


os.environ['MAUDLIN_DATA'] = _copy_database()
os.environ['MAUDLIN_NO_IMPORT'] = '1'  # the migration's file import has nothing to read in the copy's folder

import pytest  # noqa: E402

from app.utils.config import Config  # noqa: E402
from app.utils.constants import Constants  # noqa: E402
from app.site.data import DataHandler  # noqa: E402


def pytest_addoption(parser):
    parser.addoption('--setup-db', action='store_true', help='Move tests/test.db to data/data.db')


def pytest_sessionstart(session):
    if session.config.getoption('--setup-db'):
        os.rename(os.path.join(Constants.Paths.ROOT, 'tests', 'test.db'), Config.db_file_path)
    from alembic import command
    from alembic.config import Config as AlembicConfig
    command.upgrade(AlembicConfig(os.path.join(Constants.Paths.ROOT, 'alembic.ini')), 'head')  # the copy, migrated
    Config.set_debug()
    assert Config.debug
    # Pages the tests render go to a scratch folder, never the real build: the pre-commit hook runs these tests, and
    # pages written without the build's setup (icons, ratings) were overwriting the preview
    Config.build = tempfile.mkdtemp(prefix='maudlin-test-build-')
    # No test talks to the real language model: it would load the model on the shared GPU (pushing out the hourly
    # run's transcription) and make results depend on it. Tests that need answers fake llm.backend themselves.
    from app.analysis import llm
    llm.backend = lambda: None
    # Nor the embedding model behind stories (also on the shared GPU, and its cache is in the shared data folder):
    # stories fall back to the static model, as they would with Ollama down
    from app.analysis import clustering

    def no_ollama(*args, **kwargs):
        raise RuntimeError('no Ollama embeddings in tests')
    clustering.ollama_embed = no_ollama
    # Nor Bluesky's API (its lookups are in data.db): no posts to show
    from app import bluesky_examples
    bluesky_examples.prepared = dict
    # Nor the accusations screen's model (its cache is in the shared data folder too): no one accused
    from app.analysis import accusations
    accusations.read = lambda claim: {'accused': []}
    # Stories' return verdicts live in the shared data folder too
    from app.analysis import stories
    stories.RETURNS = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-stories-'), 'story_returns.json')
    accusations.PER_BUILD = 10 ** 6  # the suite shares one screen: no budget to run out of
    accusations.CACHE = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-accuse-'), 'accusations.json')
    # The motif retriever's weights live there too; filing in tests uses the closest motifs unless a test trains it
    from app.analysis import motif_retriever
    motif_retriever.WEIGHTS = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-retriever-'), 'motif_retriever.json')
    motif_retriever.MIN_FILINGS = 10 ** 6
    # The motif signals' caches (claim shapes, reranker and yes/no answers) too
    from app.analysis import motif_signals
    sig = tempfile.mkdtemp(prefix='maudlin-test-signals-')
    motif_signals.SHAPES, motif_signals.RERANKS, motif_signals.JUDGED = (os.path.join(sig, n) for n in ('s.json', 'r.json', 'j.json'))
    # The curation database (index versions, checkpoints, the log) too
    from app.analysis import curation_db
    curation_db.DB = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-curation-'), 'curation.sqlite')
    # The filing confidence model lives there too
    from app.analysis import filing_confidence
    filing_confidence.MODEL = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-confidence-'), 'filing_confidence.json')
    # Story pages kept for good: in the shared data folder too
    from app.site import page_story
    page_story.ARCHIVE = tempfile.mkdtemp(prefix='maudlin-test-story-archive-')


# Every path into the shared data folder, pointed at a scratch copy (Oct 14: the list above missed the shortlist and
# filing logs, and 81 test runs since Oct 12 wrote "Biden is too old to govern" and the like into the real ones, which
# the weekly shortlist check reads). Not path by path: before each test, any module-level path under the data folder,
# in any module loaded so far, and the data folder itself, now lead to the same place under a scratch folder.
SCRATCH = tempfile.mkdtemp(prefix='maudlin-test-data-')
_REAL = None
_done = set()


def _real_roots() -> tuple:
    global _REAL
    if _REAL is None:
        # the real folder, and the database copy's folder (paths built from Config.data at import lead there)
        _REAL = tuple({os.path.realpath(_REAL_DATA), os.path.abspath(_REAL_DATA),
                       os.path.realpath(os.environ['MAUDLIN_DATA'])})
    return _REAL


_real_roots()  # now, while Config.data is still the real folder


def _scratch(path: str) -> str | None:
    for root in _real_roots():
        if path == root or path.startswith(root + os.sep):
            new = SCRATCH + path[len(root):]
            os.makedirs(os.path.dirname(new) if os.path.splitext(new)[1] else new, exist_ok=True)
            return new
    return None


def _redirect_data_paths():
    import sys
    _real_roots()
    if Config.data != SCRATCH:
        Config.data = SCRATCH
        Config.cache = os.path.join(SCRATCH, 'cache')  # read at call time by some (page_headlines' story seams)
    for name, mod in list(sys.modules.items()):
        if name in _done or not (name.startswith('app') or getattr(mod, '__file__', '') and
                                 os.sep + 'scripts' + os.sep in (mod.__file__ or '')):
            continue
        _done.add(name)
        for attr, val in list(vars(mod).items()):
            if isinstance(val, str) and not val.endswith('.db') and (new := _scratch(os.path.abspath(val)) if val.startswith('/') else None):
                setattr(mod, attr, new)


@pytest.fixture(autouse=True)
def _no_shared_data():
    _redirect_data_paths()
    yield


# And a backstop for what the redirect can't see (Oct 22: scripts/validate.py, loaded by file and never registered as a
# module, kept its real verdict log, and 408 fake "no" answers from test_curation_db reached the person's dashboard):
# any file opened for writing under the real data folder fails the test that opens it, naming the file
_open = open


def _guarded_open(file, mode='r', *args, **kwargs):
    if isinstance(file, (str, os.PathLike)) and any(c in mode for c in 'wax+'):
        path = os.path.realpath(os.fspath(file))
        if any(path == root or path.startswith(root + os.sep) for root in _real_roots()):
            raise PermissionError(f'a test wrote into the real data folder: {path}')
    return _open(file, mode, *args, **kwargs)


@pytest.fixture(autouse=True, scope='session')
def _no_writes_to_shared_data():
    import builtins
    import io
    builtins.open, io.open = _guarded_open, _guarded_open
    yield
    builtins.open, io.open = _open, _open


@pytest.fixture(scope='session')
def data_handler():
    return DataHandler()
