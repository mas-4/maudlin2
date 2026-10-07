import os
import tempfile

# Before any app module sets up its logger: test runs (the pre-commit hook included) must not write into the real
# log, which lives in the data folder prod shares
os.environ['MAUDLIN_LOG_FILE'] = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-log-'), 'app.log')

import pytest  # noqa: E402

from app.utils.config import Config  # noqa: E402
from app.utils.constants import Constants  # noqa: E402
from app.site.data import DataHandler  # noqa: E402


def pytest_addoption(parser):
    parser.addoption('--setup-db', action='store_true', help='Move tests/test.db to data/data.db')


def pytest_sessionstart(session):
    if session.config.getoption('--setup-db'):
        os.rename(os.path.join(Constants.Paths.ROOT, 'tests', 'test.db'), Config.db_file_path)
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
    # Nor Bluesky's API (and its cache is in the shared data folder): no posts to show
    from app import bluesky_examples
    bluesky_examples.prepared = dict
    bluesky_examples.CACHE = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-bsky-'), 'bluesky_examples.json')
    # Nor the accusations screen's model (its cache is in the shared data folder too): no one accused
    from app.analysis import accusations
    accusations.read = lambda claim: {'accused': []}
    # Stories' return verdicts and merges live in the shared data folder too
    from app.analysis import stories
    scratch = tempfile.mkdtemp(prefix='maudlin-test-stories-')
    stories.RETURNS, stories.MERGES = os.path.join(scratch, 'story_returns.json'), os.path.join(scratch, 'story_merges.json')
    accusations.PER_BUILD = 10 ** 6  # the suite shares one screen: no budget to run out of
    accusations.CACHE = os.path.join(tempfile.mkdtemp(prefix='maudlin-test-accuse-'), 'accusations.json')


@pytest.fixture(scope='session')
def data_handler():
    return DataHandler()
