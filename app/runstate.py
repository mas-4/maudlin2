"""Small named values the processes pass each other, kept in data.db's run_state table (Nov 1; they were JSON files
in the data folder): the worker's heartbeat, the GPU lease, the news day, a feed's ETags. Each is one JSON value,
read and written whole.

    get(name, default)      the value, or a fresh copy of default
    when(name)              when it was last written (naive UTC), or None
    put(name, value)        replace it (or inside a session's own transaction)
    update(name, fn)        read, change and write in one transaction: no other process writes in between
    delete(name)

Names are the old files' names without .json ('worker', 'gpu_lease', 'chyrons/state')."""
import copy
import json
from datetime import datetime as dt, UTC

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.dialects.sqlite import insert

GONE = object()  # update()'s fn returns this to remove the value


def _now() -> dt:
    return dt.now(UTC).replace(tzinfo=None)


def _default(default):
    return default() if callable(default) else copy.deepcopy(default)


def get(name: str, default=None):
    from app.models import Session
    from app.tables.runstate import RunState
    with Session() as s:
        raw = s.scalar(select(RunState.value).where(RunState.name == name))
    try:
        value = json.loads(raw) if raw is not None else None
    except ValueError:
        value = None
    return _default(default) if value is None else value


def when(name: str) -> dt | None:
    from app.models import Session
    from app.tables.runstate import RunState
    with Session() as s:
        return s.scalar(select(RunState.at).where(RunState.name == name))


def _upsert(s, name: str, value):
    from app.tables.runstate import RunState
    q = insert(RunState).values(name=name, value=json.dumps(value), at=_now())
    s.execute(q.on_conflict_do_update(index_elements=['name'], set_={'value': q.excluded.value, 'at': q.excluded.at}))


def put(name: str, value, session=None):
    """Replace it; inside `session`'s transaction when given (committed by the caller with its other writes)"""
    if session is not None:
        _upsert(session, name, value)
        return
    from app.models import Session
    with Session() as s:
        _upsert(s, name, value)
        s.commit()


def delete(name: str):
    from app.models import Session
    from app.tables.runstate import RunState
    with Session() as s:
        s.execute(sql_delete(RunState).where(RunState.name == name))
        s.commit()


def update(name: str, fn, default=None):
    """fn(value) -> the new value (or GONE), applied in one write transaction; returns what fn returned. An exception
    in fn leaves the value as it was. The transaction begins with a write, so SQLite takes the write lock before the
    read and another process's update waits for this one instead of both reading the old value"""
    from app.models import Session
    from app.tables.runstate import RunState
    with Session() as s:
        # A no-op write first: it takes the write lock, so the read below sees the latest value
        s.execute(insert(RunState).values(name=name, value='null', at=_now()).on_conflict_do_nothing())
        raw = s.scalar(select(RunState.value).where(RunState.name == name))
        current = json.loads(raw) if raw not in (None, 'null') else _default(default)
        try:
            new = fn(current)
        except BaseException:
            s.rollback()
            raise
        if new is GONE:
            s.execute(sql_delete(RunState).where(RunState.name == name))
        else:
            _upsert(s, name, new)
        s.commit()
        return new
