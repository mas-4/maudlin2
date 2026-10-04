import os
import tempfile

import pytest

from app.utils.config import Config
from app.utils.constants import Constants
from app.site.data import DataHandler


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


@pytest.fixture(scope='session')
def data_handler():
    return DataHandler()
