"""Tables for the stories group (see app/tables/__init__.py): what happened to stories and sagas beyond the story and
saga tables (merges, splits, when each was titled, sagas that ended and where their pages point), the saga judge's
verdicts on pairs of stories, what each story page gathered while the story was on the front page, and the name
aliases the person keeps on the checker's names page."""
from datetime import datetime as dt

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, DateTime, Integer, Text

from app.models import Base


class StoryMerge(Base):
    """A story folded into another (stories.merge_stories): the gone story's id lives on, so its page redirects and
    data keyed by it follow. No foreign keys: the gone story's row is deleted"""
    __tablename__ = 'story_merge'
    gone: Mapped[int] = mapped_column(Integer(), primary_key=True)
    into: Mapped[int] = mapped_column(Integer(), index=True)
    label: Mapped[str | None] = mapped_column(Text(), nullable=True)  # the gone story's title then
    first_seen: Mapped[dt | None] = mapped_column(DateTime(), nullable=True)
    headlines: Mapped[str] = mapped_column(Text(), default='[]')  # JSON list of the headline ids that moved
    at: Mapped[dt] = mapped_column(DateTime())  # naive UTC
    why: Mapped[str] = mapped_column(Text(), default='')


class StorySplit(Base):
    """A story ended at a new development (stories.split_development): its newest headlines went on as `into`"""
    __tablename__ = 'story_split'
    story_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    into: Mapped[int] = mapped_column(Integer(), index=True)
    label: Mapped[str | None] = mapped_column(Text(), nullable=True)
    since: Mapped[dt] = mapped_column(DateTime())  # its last title, the split's line
    headlines: Mapped[str] = mapped_column(Text(), default='[]')  # JSON list of the headline ids that moved
    at: Mapped[dt] = mapped_column(DateTime())


class StoryLabeledAt(Base):
    """When a story's title was last written (naive UTC), so a live story is titled again once its news moves on"""
    __tablename__ = 'story_labeled_at'
    story_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    at: Mapped[dt] = mapped_column(DateTime())


class StoryFinalLabel(Base):
    """A story titled once more after it left the front pages (stories.label_ended), and the title it replaced"""
    __tablename__ = 'story_final_label'
    story_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    at: Mapped[dt] = mapped_column(DateTime())
    replaced: Mapped[str | None] = mapped_column(Text(), nullable=True)


class SagaEnded(Base):
    """A saga gone (absorbed into another, or left with one part or none): where its page now points"""
    __tablename__ = 'saga_ended'
    saga_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    to_saga: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    to_story: Mapped[int | None] = mapped_column(Integer(), nullable=True)


class SagaPair(Base):
    """The saga judge's verdict on a pair of saved stories (sagas.pair_verdict), asked once per pair and judge version;
    a person's verdict (hand) is never asked again"""
    __tablename__ = 'saga_pair'
    story_a: Mapped[int] = mapped_column(Integer(), primary_key=True)  # the smaller id
    story_b: Mapped[int] = mapped_column(Integer(), primary_key=True)
    same: Mapped[bool] = mapped_column(Boolean())
    judge: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    hand: Mapped[bool] = mapped_column(Boolean(), default=False)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    at: Mapped[dt | None] = mapped_column(DateTime(), nullable=True)
    titles_a: Mapped[str] = mapped_column(Text(), default='[]')  # JSON: two of each side's headlines, as shown
    titles_b: Mapped[str] = mapped_column(Text(), default='[]')


class StoryExtra(Base):
    """What the front page found around a saved story, kept for its page after it leaves (page_headlines
    .save_story_extras); the lists are StoryExtraItem rows"""
    __tablename__ = 'story_extra'
    story_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    wording: Mapped[str] = mapped_column(Text(), default='{}')  # JSON: one-sided wording by side, the latest run's
    updated: Mapped[dt] = mapped_column(DateTime())


class StoryExtraItem(Base):
    """One thing found around a story: a show, fact-check, investigation or satire piece on it, an aggregator linking
    it, a quote. Every item ever found is kept; listed newest found first, then in the run's order"""
    __tablename__ = 'story_extra_item'
    story_id: Mapped[int] = mapped_column(Integer(), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), primary_key=True)  # shows, factchecks, ..., curators, quotes
    key: Mapped[str] = mapped_column(Text(), primary_key=True)  # its url, else source; a quote's phrase
    source: Mapped[str | None] = mapped_column(Text(), nullable=True)
    title: Mapped[str | None] = mapped_column(Text(), nullable=True)
    url: Mapped[str | None] = mapped_column(Text(), nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    emoji: Mapped[str | None] = mapped_column(String(16), nullable=True)
    count: Mapped[int | None] = mapped_column(Integer(), nullable=True)  # a quote's
    seen: Mapped[dt] = mapped_column(DateTime(), index=True)  # the run that last found it
    ord: Mapped[int] = mapped_column(Integer(), default=0)  # its place in that run's list


class EntityAlias(Base):
    """A name the person said is another name for a subject, or a subject renamed (entities.merge, on the checker's
    names page); the seed aliases stay in the code"""
    __tablename__ = 'entity_alias'
    name: Mapped[str] = mapped_column(Text(), primary_key=True)  # lower case
    target: Mapped[str] = mapped_column(Text())


class EntityNotSame(Base):
    """Two names the person said are different subjects, never to be suggested as one"""
    __tablename__ = 'entity_not_same'
    a: Mapped[str] = mapped_column(Text(), primary_key=True)  # the pair sorted
    b: Mapped[str] = mapped_column(Text(), primary_key=True)
