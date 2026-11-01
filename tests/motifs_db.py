"""An in-memory data.db for tests of what moved into it from the data folder (Nov 1): every table made, app.models'
Session pointed at it for the test."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool


def memory_db(monkeypatch):
    import app.models as models
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(models, 'Session', session)
    return session
