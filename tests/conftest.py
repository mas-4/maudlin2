import os
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


@pytest.fixture(scope='session')
def data_handler():
    return DataHandler()
