"""Tables for the records group (see app/tables/__init__.py): VoteHub's polls, the Bluesky posts looked up for the
site, the word cloud's words each run, each scraper's numbers each run, and the news-day score each hour."""
from datetime import datetime as dt

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, DateTime, Float, Integer, Text

from app.models import Base


class Poll(Base):
    """One poll from VoteHub's feed (app/polling.py), as the feed gave it; the whole feed replaces these each fetch"""
    __tablename__ = 'poll'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # VoteHub's own
    poll_type: Mapped[str] = mapped_column(String(32), index=True)
    subject: Mapped[str | None] = mapped_column(Text(), nullable=True)
    pollster: Mapped[str | None] = mapped_column(Text(), nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    population: Mapped[str | None] = mapped_column(String(8), nullable=True)
    url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[str | None] = mapped_column(String(10), nullable=True)  # the feed's dates, YYYY-MM-DD
    start_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    end_date: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)
    seat_name: Mapped[str | None] = mapped_column(Text(), nullable=True)
    sponsors: Mapped[str] = mapped_column(Text(), default='[]')  # JSON list of names
    internal: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    partisan: Mapped[str | None] = mapped_column(String(8), nullable=True)
    fetched: Mapped[dt] = mapped_column(DateTime())  # when we took it from the feed (naive UTC)


class PollAnswer(Base):
    """One choice in a poll and its share"""
    __tablename__ = 'poll_answer'
    id: Mapped[int] = mapped_column(primary_key=True)
    poll_id: Mapped[str] = mapped_column(ForeignKey('poll.id'), index=True)
    choice: Mapped[str] = mapped_column(Text())
    pct: Mapped[float | None] = mapped_column(Float(), nullable=True)


class BlueskyPost(Base):
    """What Bluesky's public API said about a post a narrative report named (app/bluesky_examples.py), and when"""
    __tablename__ = 'bluesky_post'
    uri: Mapped[str] = mapped_column(String(255), primary_key=True)  # at://did/app.bsky.feed.post/rkey
    cid: Mapped[str | None] = mapped_column(String(128), nullable=True)
    did: Mapped[str | None] = mapped_column(String(128), nullable=True)
    handle: Mapped[str | None] = mapped_column(Text(), nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer(), nullable=True)  # null until Bluesky answered for it
    reposts: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    quotes: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    replies: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    followers: Mapped[int | None] = mapped_column(Integer(), nullable=True)  # only looked up for borderline posts
    hidden: Mapped[bool] = mapped_column(Boolean(), default=False)  # a moderation or no-logged-out label
    gone: Mapped[bool] = mapped_column(Boolean(), default=False)  # deleted or hidden since
    checked: Mapped[dt] = mapped_column(DateTime())  # last looked up (naive UTC)
    first: Mapped[dt] = mapped_column(DateTime(), index=True)  # first looked up


class CloudWord(Base):
    """A word in the front page's word cloud at one production run, in the cloud's order (app/site/wordcloudgen.py)"""
    __tablename__ = 'cloud_word'
    __table_args__ = (Index('ix_cloud_word_at_rank', 'at', 'rank'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt] = mapped_column(DateTime())  # the run's (naive UTC)
    rank: Mapped[int] = mapped_column(Integer())  # 0 the biggest
    word: Mapped[str] = mapped_column(Text())


class ScraperRun(Base):
    """One scraper's numbers at one hourly run (app/scraper_health.py)"""
    __tablename__ = 'scraper_run'
    __table_args__ = (Index('ix_scraper_run_agency_at', 'agency', 'at'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    agency: Mapped[str] = mapped_column(String(64))
    at: Mapped[dt] = mapped_column(DateTime())  # local time, to the minute, as the check file shows it
    url: Mapped[str] = mapped_column(Text())
    found: Mapped[int] = mapped_column(Integer(), default=0)
    kept: Mapped[int] = mapped_column(Integer(), default=0)
    added: Mapped[int] = mapped_column(Integer(), default=0)
    too_long: Mapped[int] = mapped_column(Integer(), default=0)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)


class NewsinessPoint(Base):
    """The news-day score at one hourly run and the story it was highest for (app/analysis/newsiness.py): recorded by
    the build itself from Oct 12, reconstructed from the database before then"""
    __tablename__ = 'newsiness_point'
    __table_args__ = (Index('ix_newsiness_point_made_at', 'made', 'at'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    made: Mapped[str] = mapped_column(String(16))  # 'recorded' or 'reconstructed'
    at: Mapped[dt] = mapped_column(DateTime())  # naive UTC
    score: Mapped[float] = mapped_column(Float())
    share: Mapped[float] = mapped_column(Float())
    outlets: Mapped[int] = mapped_column(Integer())
    active: Mapped[int] = mapped_column(Integer())
    story_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)  # no foreign key: stories can be merged away
    label: Mapped[str] = mapped_column(Text(), default='')
    kind: Mapped[str] = mapped_column(String(8))

