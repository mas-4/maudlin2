from datetime import datetime as dt, timedelta as td
from threading import Lock
from typing import Optional, cast

import numpy as np
import pytz
from sqlalchemy import ForeignKey, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, scoped_session, sessionmaker
from sqlalchemy.types import Boolean, Text, Float, DateTime, Integer

from app.utils import Config, Bias, Credibility, Country, Constants, get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


class Agency(Base):
    __tablename__ = "agency"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30), index=True)
    url: Mapped[str] = mapped_column(String(100))
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="agency", lazy="dynamic")
    _bias: Mapped[int] = mapped_column(Integer())
    _credibility: Mapped[int] = mapped_column(Integer())  # legacy MBFC rating, no longer shown
    _country: Mapped[int] = mapped_column(Integer())
    # Licensed ratings from ratings.csv (see app/ratings.py): AllSides lean, stored in _bias as -2..2, and Wikipedia's
    # reliability status. An outlet AllSides doesn't rate has lean_rated False and a placeholder _bias of 0.
    lean_rated: Mapped[bool] = mapped_column(Boolean(), default=False, server_default='0')
    lean_url: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    reliability: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reliability_note: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    def __repr__(self) -> str:
        return f"Agency(id={self.id!r}, name={self.name!r}, url={self.url!r})"

    def current(self, col) -> float:
        with (Session() as s):
            last_accessed = Config.last_accessed
            if Config.debug:
                last_accessed = s.query(Headline.last_accessed).order_by(Headline.last_accessed.desc()).first()[0]
                last_accessed = last_accessed - td(minutes=25)
            first_date_filter = Article.first_accessed > s.query(Article.first_accessed).filter_by(agency_id=self.id) \
                .order_by(Article.first_accessed.asc()).first()[0] + td(days=1)  # to eliminate permanent links
            base_query = s.query(col).join(Article, Article.id == Headline.article_id).filter_by(
                agency_id=self.id).filter(first_date_filter).order_by(Headline.last_accessed.desc())
            data = base_query.filter(Headline.last_accessed > last_accessed).all()
            numbers = np.array(data).flatten()
        if np.isnan(np.mean(numbers)):
            logger.warning("No %s data for %r.", col, self)
        return np.mean(numbers[~np.isnan(numbers)])

    def current_vader(self) -> float:
        return self.current(Headline.vader_compound)

    def current_afinn(self) -> float:
        return self.current(Headline.afinn)

    def todays_churn(self, s) -> float:
        # divide todays headlines by todays articles
        first_date = dt.now(pytz.UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        articles = s.query(Article).filter(
            Article.agency_id == self.id,
            Article.first_accessed > first_date,
            Article.last_accessed > Constants.TimeConstants.midnight
        ).count()
        headlines = s.query(Headline).join(Article).filter(
            Article.agency_id == self.id,
            Headline.first_accessed > first_date,
            Headline.last_accessed > Constants.TimeConstants.midnight
        ).count()
        return headlines / articles if articles else 1

    @property
    def bias(self):
        return Bias(self._bias)

    @bias.setter
    def bias(self, value):
        self._bias = value.value

    @property
    def credibility(self):
        return Credibility(self._credibility)

    @credibility.setter
    def credibility(self, value):
        self._credibility = value.value

    @property
    def country(self):
        return Country(self._country)

    @country.setter
    def country(self, value):
        self._country = value.value


class AccessTimeMixin:
    first_accessed: Mapped[dt] = mapped_column(DateTime(), default=dt.now(pytz.UTC))
    last_accessed: Mapped[dt] = mapped_column(DateTime(), default=dt.now(pytz.UTC))

    def update_last_accessed(self):
        self.last_accessed = dt.now(pytz.UTC)  # noqa type: ignore


class Article(Base, AccessTimeMixin):
    __tablename__ = "article"
    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agency.id"))
    agency: Mapped["Agency"] = relationship(Agency, back_populates="articles")
    url: Mapped[str] = mapped_column(String(254), index=True)
    headlines: Mapped[list["Headline"]] = relationship("Headline", back_populates="article")
    topic_id: Mapped[int] = mapped_column(ForeignKey("topic.id"), nullable=True)
    topic: Mapped["Topic"] = relationship("Topic")
    topic_score: Mapped[float] = mapped_column(Float(), nullable=True)

    def __repr__(self) -> str:
        return f"Article(id={self.id!r}, agency={self.agency.name!r}, url={self.url!r})"

    def __str__(self) -> str:
        return self.url

    def single_doc(self):
        return '\n\n'.join([h.title for h in self.headlines])

    def most_recent_headline(self):
        return max(self.headlines, key=lambda h: h.last_accessed)


class Headline(Base, AccessTimeMixin):
    __tablename__ = "headline"
    # Mapping to article
    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id"))
    article: Mapped["Article"] = relationship(Article, back_populates="headlines")

    # Headline data
    raw: Mapped[str] = mapped_column(Text(), nullable=True)
    title: Mapped[str] = mapped_column(Text())
    processed: Mapped[str] = mapped_column(Text(), nullable=True, index=True)
    position: Mapped[int] = mapped_column(Integer(), default=0, nullable=True)

    # sentiment analysis
    vader_neg: Mapped[float] = mapped_column(Float(), nullable=True)
    vader_neu: Mapped[float] = mapped_column(Float(), nullable=True)
    vader_pos: Mapped[float] = mapped_column(Float(), nullable=True)
    vader_compound: Mapped[float] = mapped_column(Float(), nullable=True)
    afinn: Mapped[float] = mapped_column(Float(), nullable=True)

    # Internal flags
    legacy: Mapped[bool] = mapped_column(Integer(), default=0, nullable=False)
    # Probability this is a news headline rather than lifestyle, shopping or page furniture. Null until the
    # news classifier has a model to score it with; analyses treat null as news.
    news_score: Mapped[float] = mapped_column(Float(), nullable=True)
    # From the llm's rubric (see app/analysis/newsfilter.py): how good or bad the reported event is for the people
    # it affects (-2 to 2), and how loaded the outlet's own wording is (0 to 2). Null without an llm.
    event_score: Mapped[float] = mapped_column(Float(), nullable=True)
    loaded_score: Mapped[float] = mapped_column(Float(), nullable=True)
    # The emotion the headline is most likely to stir in a reader (fear, anger, sadness, disgust, surprise, joy,
    # hope or neutral), from the same llm call. Null without an llm.
    emotion: Mapped[str] = mapped_column(String(16), nullable=True)
    # Up to three emotions, strongest first, comma separated; averaged ranked-choice style (newsfilter.emotion_weights)
    emotion_ranks: Mapped[str] = mapped_column(String(64), nullable=True)
    # Provenance for the scores above, so scores from different models or rubrics never mix silently: which judge
    # made them (e.g. "qwen3:8b rubric:1a2b3c4d", the rubric id being a hash of the prompt and schema, or
    # "fallback classifier"), when, and the model's own note on who the event affects (written before it scores).
    scored_by: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    scored_at: Mapped[dt] = mapped_column(DateTime(), nullable=True)
    affected: Mapped[str] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:
        return f"Headline(id={self.id!r}, agency={self.article.agency.name!r}, title={self.processed!r})"

    def __str__(self) -> str:
        return self.title


class Topic(Base, AccessTimeMixin):
    __tablename__ = "topic"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    _keywords: Mapped[str] = mapped_column(Text())
    _essential: Mapped[str] = mapped_column(Text())

    def __repr__(self):
        return f"Topic(id={self.id!r}, name={self.name!r})"

    @property
    def keywords(self) -> list[str]:
        return self._keywords.split(',')

    @keywords.setter
    def keywords(self, value: list[str]):
        self._keywords = cast(Mapped[str], ','.join(value))

    @property
    def essential(self) -> list[str]:
        return self._essential.split(',')

    @essential.setter
    def essential(self, value: list[str]):
        self._essential = cast(Mapped[str], ','.join(value))



class Trend(Base, AccessTimeMixin):
    """Something trending outside the press: a Bluesky topic, a Google search, a most-read Wikipedia article or a
    link shared on Mastodon. One row per trend, refreshed each time it shows up in its source's list."""
    __tablename__ = "trend"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True, default='bluesky')
    topic: Mapped[str] = mapped_column(String(64), index=True, unique=True)  # stable id, prefixed by source
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text(), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=True)
    link: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=True)
    post_count: Mapped[int] = mapped_column(Integer(), nullable=True)
    rank: Mapped[int] = mapped_column(Integer(), nullable=True)
    started_at: Mapped[dt] = mapped_column(DateTime(), nullable=True)

    def __repr__(self):
        return f"Trend(id={self.id!r}, display_name={self.display_name!r})"


class TrendSighting(Base):
    """Each time a trend shows up in its source's list, with its rank then: the trend table keeps only the first
    and latest sighting, which can't say how attention rose and fell day by day (press vs. public, #117)."""
    __tablename__ = "trend_sighting"
    id: Mapped[int] = mapped_column(primary_key=True)
    trend_id: Mapped[int] = mapped_column(ForeignKey("trend.id"), index=True)
    seen_at: Mapped[dt] = mapped_column(DateTime(), index=True)
    rank: Mapped[int] = mapped_column(Integer(), nullable=True)
    post_count: Mapped[int] = mapped_column(Integer(), nullable=True)


class SideItem(Base):
    """An item from a newsletter, podcast or political video channel (app/sidefeeds.py), kept for the long run: one
    row per source and url, never overwritten. Only some sources are shown on the site; all are archived."""
    __tablename__ = "side_item"
    __table_args__ = (UniqueConstraint('source', 'url', name='uq_side_item_source_url'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)  # sidefeeds.SOURCES key
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(500))
    published: Mapped[dt] = mapped_column(DateTime(), nullable=True, index=True)
    summary: Mapped[str] = mapped_column(Text(), nullable=True)
    audio: Mapped[str] = mapped_column(String(500), nullable=True)  # a podcast's audio file, for transcribing later
    first_seen: Mapped[dt] = mapped_column(DateTime())


class SideTranscript(Base):
    """A podcast item's transcript, made on our own GPU (app/transcribe.py), with the model that made it. For
    analysis only; transcripts are never republished."""
    __tablename__ = "side_transcript"
    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("side_item.id"), unique=True)
    model: Mapped[str] = mapped_column(String(64))
    created: Mapped[dt] = mapped_column(DateTime())
    seconds: Mapped[float] = mapped_column(Float())  # the audio's length
    text: Mapped[str] = mapped_column(Text())  # sponsor reads trimmed
    segments: Mapped[str] = mapped_column(Text())  # JSON: [{start, end, text}, ...]


class Saga(Base):
    """One running story told in several parts, kept across days (app/analysis/sagas.py): stories join it and stay,
    so a saga only grows or merges into another, never loses a part when its older parts leave the front pages."""
    __tablename__ = "saga"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=True)
    named_with: Mapped[int] = mapped_column(Integer(), nullable=True)  # parts when the name was written
    words: Mapped[str] = mapped_column(String(255), nullable=True)  # its distinctive words, comma separated
    first_seen: Mapped[dt] = mapped_column(DateTime())
    last_seen: Mapped[dt] = mapped_column(DateTime())


class Story(Base):
    """One news event as covered across outlets, persisted across runs so it can be labeled once and its
    coverage compared over time. Clusters from each run are matched to stories by the headlines they share."""
    __tablename__ = "story"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(255), nullable=True)  # neutral title written by the llm
    labeled_with: Mapped[int] = mapped_column(Integer(), nullable=True)  # outlet count when the label was written
    first_seen: Mapped[dt] = mapped_column(DateTime())
    last_seen: Mapped[dt] = mapped_column(DateTime())
    saga_id: Mapped[Optional[int]] = mapped_column(ForeignKey("saga.id"), nullable=True, index=True)
    headlines: Mapped[list["StoryHeadline"]] = relationship("StoryHeadline", back_populates="story")

    def __repr__(self):
        return f"Story(id={self.id!r}, label={self.label!r})"


class StorySnapshot(Base):
    """A story's meters at one run (lean of the outlets covering it, mood, outlets), for trend arrows on its card and
    for studying how coverage of a story moves over its life."""
    __tablename__ = "story_snapshot"
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("story.id"), index=True)
    at: Mapped[dt] = mapped_column(DateTime(), index=True)
    lean: Mapped[float] = mapped_column(Float())  # relative to the day's outlets, as on the card
    mood: Mapped[float] = mapped_column(Float())
    outlets: Mapped[int] = mapped_column(Integer())


class StoryHeadline(Base):
    """A headline's membership in a story, with how its sentiment compares to the other outlets on that story."""
    __tablename__ = "story_headline"
    id: Mapped[int] = mapped_column(primary_key=True)
    story_id: Mapped[int] = mapped_column(ForeignKey("story.id"), index=True)
    story: Mapped["Story"] = relationship(Story, back_populates="headlines")
    headline_id: Mapped[int] = mapped_column(ForeignKey("headline.id"), unique=True)
    sentiment: Mapped[float] = mapped_column(Float())
    deviation: Mapped[float] = mapped_column(Float())  # sentiment minus the story's mean across outlets
    last_seen: Mapped[dt] = mapped_column(DateTime())


engine = create_engine(Config.connection_string)
# Keeping this after migrating to alembic
# Running this would create the tables in the database but not mark alembic upgrades
# So just don't do it. To upgrade the database run alembic upgrade head
# Base.metadata.create_all(engine)

session_factory = sessionmaker(bind=engine, autoflush=False)
Session = scoped_session(session_factory)
SqlLock = Lock()
