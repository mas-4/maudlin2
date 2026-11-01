"""Tables for the narratives group (see app/tables/__init__.py): the nightly narrative reports (app/narratives.py),
the narratives withheld by hand, the threads that follow a narrative across days (app/analysis/narrative_threads.py)
and the TV captions matched to stories (app/chyrons.py)."""
import json

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, Float, Integer, Text

from app.models import Base


class NarrativeReport(Base):
    """One narrative report: a run over the last `hours` of posts. Its file name (report-YYYY-MM-DD-HHMM.json) stays
    its key, as the threads and the filings' refs name reports by it"""
    __tablename__ = 'narrative_report'
    file: Mapped[str] = mapped_column(String(40), primary_key=True)
    made: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)  # 2026-10-05T08:17, Eastern
    hours: Mapped[float | None] = mapped_column(Float(), nullable=True)
    posts: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    authors: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    groups: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    kinds: Mapped[str | None] = mapped_column(Text(), nullable=True)  # JSON: {kind: groups}
    focus_group_segments: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    threads_linked: Mapped[bool] = mapped_column(Boolean(), default=False, server_default='0')


class NarrativeGroup(Base):
    """One paraphrase group of a report, in the report's order (most people first). label and story hold JSON text,
    'null' where the report said None and SQL NULL where it had no such key; parts holds the group's other keys
    (shared links, examples, post keys and uris, voters, articles, fact-checks...), all read whole"""
    __tablename__ = 'narrative_group'
    id: Mapped[int] = mapped_column(primary_key=True)
    report: Mapped[str] = mapped_column(String(40), ForeignKey('narrative_report.file', ondelete='CASCADE'))
    position: Mapped[int] = mapped_column(Integer())
    kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    posts: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    authors: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    variety: Mapped[float | None] = mapped_column(Float(), nullable=True)
    replies: Mapped[float | None] = mapped_column(Float(), nullable=True)
    # From the label and the story tie, to find a claim or a story's narratives without reading every group
    narrative: Mapped[str | None] = mapped_column(Text(), nullable=True, index=True)
    retold: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    story_id: Mapped[int | None] = mapped_column(Integer(), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(Text(), nullable=True)
    story: Mapped[str | None] = mapped_column(Text(), nullable=True)
    parts: Mapped[str] = mapped_column(Text(), default='{}')
    __table_args__ = (Index('ix_narrative_group_report', 'report', 'position'),)


class NarrativeWithheld(Base):
    """A narrative's claim pulled from the pages by hand after a misreading"""
    __tablename__ = 'narrative_withheld'
    claim: Mapped[str] = mapped_column(Text(), primary_key=True)
    reason: Mapped[str] = mapped_column(Text(), default='')
    at: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD


class NarrativeThreadDay(Base):
    """One day a thread's narrative was told: the thread's id (N0001...), the day's report and the facts kept of it"""
    __tablename__ = 'narrative_thread_day'
    id: Mapped[int] = mapped_column(primary_key=True)
    thread: Mapped[str] = mapped_column(String(12), index=True)
    report: Mapped[str] = mapped_column(String(40), index=True)
    date: Mapped[str] = mapped_column(String(10), index=True)
    claim: Mapped[str] = mapped_column(Text())
    people: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    posts: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    genre: Mapped[str] = mapped_column(String(60), default='')
    story: Mapped[str | None] = mapped_column(Text(), nullable=True)  # the story's label that day


class ChyronMatch(Base):
    """A headline caption on one channel in one UTC day, with the story it was matched to, if any"""
    __tablename__ = 'chyron_match'
    id: Mapped[int] = mapped_column(primary_key=True)
    day: Mapped[str] = mapped_column(String(10), index=True)  # the UTC day it was read in
    at: Mapped[str] = mapped_column(String(19))  # ISO, UTC
    channel: Mapped[str] = mapped_column(String(12))
    seconds: Mapped[int] = mapped_column(Integer())
    program: Mapped[str] = mapped_column(Text(), default='')
    text: Mapped[str] = mapped_column(Text())
    story: Mapped[int | None] = mapped_column(Integer(), nullable=True, index=True)
    label: Mapped[str | None] = mapped_column(Text(), nullable=True)
    rank: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    outlets: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    score: Mapped[float | None] = mapped_column(Float(), nullable=True)  # embedding match only, not the model's


# The report's and its groups' JSON shapes, to and from rows (shared by app/narratives.py and the import)
REPORT_FIELDS = ('made', 'hours', 'posts', 'authors', 'groups', 'focus_group_segments')
GROUP_FIELDS = ('kind', 'posts', 'authors', 'variety', 'replies')
MATCH_FIELDS = ('at', 'channel', 'seconds', 'program', 'text', 'story', 'label', 'rank', 'outlets', 'score')


def report_row(file: str, report: dict) -> dict:
    row = {f: report.get(f) for f in REPORT_FIELDS}
    return dict(row, file=file, kinds=json.dumps(report['kinds']) if 'kinds' in report else None)


def group_rows(file: str, groups: list[dict]) -> list[dict]:
    out = []
    for n, g in enumerate(groups):
        label, story = g.get('label') or {}, g.get('story') or {}
        out.append({'report': file, 'position': n, **{f: g.get(f) for f in GROUP_FIELDS},
                    'narrative': label.get('narrative') or None, 'retold': label.get('retold'),
                    'story_id': story.get('id') if isinstance(story.get('id'), int) else None,
                    'label': json.dumps(g['label']) if 'label' in g else None,
                    'story': json.dumps(g['story']) if 'story' in g else None,
                    'parts': json.dumps({k: v for k, v in g.items() if k not in GROUP_FIELDS + ('label', 'story')})})
    return out


def report_of(row: NarrativeReport, groups: list[NarrativeGroup]) -> dict:
    """The report as it was written (only the keys it had), with its file name"""
    out = {f: getattr(row, f) for f in REPORT_FIELDS if getattr(row, f) is not None}
    if row.kinds is not None:
        out['kinds'] = json.loads(row.kinds)
    return dict(out, found=[group_of(g) for g in groups], file=row.file)


def group_of(row: NarrativeGroup) -> dict:
    out = {f: getattr(row, f) for f in GROUP_FIELDS if getattr(row, f) is not None}
    for f in ('label', 'story'):
        if getattr(row, f) is not None:
            out[f] = json.loads(getattr(row, f))
    return dict(out, **json.loads(row.parts or '{}'))
