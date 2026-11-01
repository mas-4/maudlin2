"""Tables for the motifs group (see app/tables/__init__.py): the correction proposer's proposals and the person's
decisions on them, the checker's undo stack, the watch list of plain claims, and each teaching of the reranker. The
motif index itself and the curation log stay in their own databases (motif_index.sqlite, curation.sqlite)."""
from sqlalchemy import Index, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, Float, Integer, Text

from app.models import Base


class MotifProposal(Base):
    """One proposal (app/analysis/motif_proposals.py), open or decided; decided ones are kept for good, so a rejected
    proposal never comes back. The model's own noes ('link_ok', 'not_group'...) are rows too, status 'none'"""
    __tablename__ = 'motif_proposal'
    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # pid(kind, args)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(10), index=True)  # open, approved, rejected, none
    args: Mapped[str] = mapped_column(Text(), default='{}')  # JSON: the kind's own arguments, read whole
    reason: Mapped[str] = mapped_column(Text(), default='')
    model: Mapped[str] = mapped_column(String(64), default='')
    made: Mapped[str] = mapped_column(String(19), default='')  # ISO seconds, as the store always kept them
    decided: Mapped[str | None] = mapped_column(String(19), nullable=True)
    why: Mapped[str | None] = mapped_column(Text(), nullable=True)  # the person's words on what was wrong
    final: Mapped[str | None] = mapped_column(Text(), nullable=True)  # JSON: the action carried out, when not the proposal's
    judge: Mapped[str | None] = mapped_column(Text(), nullable=True)  # JSON: the judge's score {p, score, reason, model}
    fit: Mapped[float | None] = mapped_column(Float(), nullable=True)  # best fit, for the checklist's order


class CheckerUndo(Base):
    """One step on the checker's undo stack (scripts/validate.py), newest last: the managed state before it, a hash of
    the state after, and the proposals it decided"""
    __tablename__ = 'checker_undo'
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[str] = mapped_column(String(32))  # %Y%m%d-%H%M%S-%f
    path: Mapped[str] = mapped_column(Text())  # which managed thing: the motif index or the name aliases
    before: Mapped[str | None] = mapped_column(Text(), nullable=True)  # 'txn:41' for the index, else the file's text
    after_sha: Mapped[str] = mapped_column(String(40))
    after: Mapped[str | None] = mapped_column(Text(), nullable=True)  # the index's save number after it
    what: Mapped[str] = mapped_column(Text(), default='')
    proposals: Mapped[str | None] = mapped_column(Text(), nullable=True)  # JSON list of proposal ids
    log: Mapped[int | None] = mapped_column(Integer(), nullable=True)  # its row in the curation log


class WatchClaim(Base):
    """A claim on the watch list (app/analysis/watch_list.py): plain news or no motif, filed again as the index grows"""
    __tablename__ = 'watch_claim'
    key: Mapped[str] = mapped_column(String(32), primary_key=True)  # motif_index.key of its words
    claim: Mapped[str | None] = mapped_column(Text(), nullable=True)
    source: Mapped[str | None] = mapped_column(Text(), nullable=True)
    ref: Mapped[str | None] = mapped_column(Text(), nullable=True)
    date: Mapped[str | None] = mapped_column(String(10), nullable=True)  # the day it was reported (t0)
    story: Mapped[int | None] = mapped_column(Integer(), index=True, nullable=True)
    story_tie: Mapped[str | None] = mapped_column(String(32), nullable=True)
    plain: Mapped[bool] = mapped_column(Boolean(), default=False)
    why: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 'no motif', 'watched motif'
    since: Mapped[str | None] = mapped_column(String(10), nullable=True)
    refiled: Mapped[str | None] = mapped_column(String(19), nullable=True)  # the last pass


class WatchUnfound(Base):
    """A claim with no motif whose words weren't found, and the day they were last looked for"""
    __tablename__ = 'watch_unfound'
    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[str] = mapped_column(String(10))


class RerankerTeaching(Base):
    """One weekly teaching of the reranker (app/analysis/reranker_teach.py); the newest says which reranker is used.
    The taught layers themselves stay a file beside the data (motifs/reranker/taught.pt)"""
    __tablename__ = 'reranker_teaching'
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[str] = mapped_column(String(19))
    examples: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    decisions: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    taught_auc: Mapped[float | None] = mapped_column(Float(), nullable=True)
    base_auc: Mapped[float | None] = mapped_column(Float(), nullable=True)
    kept: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 'taught' or 'base'

    __table_args__ = (Index('ix_reranker_teaching_at', 'at'),)
