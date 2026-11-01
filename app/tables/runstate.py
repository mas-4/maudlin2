"""Tables for the runstate group (see app/tables/__init__.py): the small singletons the hourly run, the worker, the
checker and the dashboard pass each other (app/runstate.py), and the few that are better as rows."""
from datetime import datetime as dt

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import DateTime, Integer, Text

from app.models import Base


class RunState(Base):
    """One named value, kept whole as JSON: the worker's heartbeat, the GPU lease, a feed's ETags, the day's news
    day... Read and written through app/runstate.py"""
    __tablename__ = "run_state"
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text())
    at: Mapped[dt] = mapped_column(DateTime())  # last written (naive UTC)


class FactcheckSeen(Base):
    """A fact-checked claim looked for in the social sample by the latest nightly look (app/analysis/circulation.py);
    the look itself (hours, posts, at) is run_state 'factcheck_seen'"""
    __tablename__ = "factcheck_seen"
    url: Mapped[str] = mapped_column(Text(), primary_key=True)
    telling: Mapped[int] = mapped_column(Integer())
    arguing: Mapped[int] = mapped_column(Integer())
    people: Mapped[int] = mapped_column(Integer())
    candidates: Mapped[int] = mapped_column(Integer())
    checked: Mapped[int] = mapped_column(Integer())
    at: Mapped[str] = mapped_column(String(16))  # local time to the minute, as the look wrote it


class MotifMetricsDay(Base):
    """The motif index's shape on a day, the latest snapshot of the day (app/analysis/motif_filing.py)"""
    __tablename__ = "motif_metrics_day"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    shape: Mapped[str] = mapped_column(Text())  # JSON: flat counts and shares; keys were added over time


class ModelSeen(Base):
    """A model the weekly scout has seen, and the day it first did (scripts/model_scout.py)"""
    __tablename__ = "model_seen"
    key: Mapped[str] = mapped_column(Text(), primary_key=True)  # source:id
    first_seen: Mapped[str] = mapped_column(String(10))


class ArchiveDay(Base):
    """A day's saved front-page edition, as the front page called the day at its last run (app/site/archive.py); the
    edition itself stays a file, data/archive/<day>.html"""
    __tablename__ = "archive_day"
    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    label: Mapped[str | None] = mapped_column(Text())
    emoji: Mapped[str | None] = mapped_column(Text())
    story: Mapped[str | None] = mapped_column(Text())
    stories: Mapped[int | None] = mapped_column(Integer())
