import os

from app.utils.config import Config
from app.utils.constants import Constants


def pytest_sessionstart(session):
    # move tests/test.db to data/data.db
    Config.db = os.path.join(Config.data, 'data.db')
    Config.debug = True
    os.rename(os.path.join(Constants.Paths.ROOT, 'tests', 'test.db'), Config.db)
