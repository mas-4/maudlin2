"""Tables for the caches group (see app/tables/__init__.py). The group's other files are model answers rebuilt if
lost, kept as files in Config.cache; the fact-checks' labels are not: their claims are what the motif index files
(by claim key) and the person corrects, and pieces older than factchecks.LABEL_DAYS are never read again."""
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Boolean, Text

from app.models import Base


class FactcheckLabel(Base):
    """A fact-check read as a folklorist would (app/analysis/factchecks.label_all): the claim it checks, the way its
    tellers state it, and the narrative labels. Was data/factcheck_labels.json, url -> labels."""
    __tablename__ = "factcheck_label"
    url: Mapped[str] = mapped_column(Text(), primary_key=True)
    claim: Mapped[str] = mapped_column(Text(), default='')
    claim_from_piece: Mapped[str | None] = mapped_column(Text(), nullable=True)  # a later reading, the claim kept
    context: Mapped[str | None] = mapped_column(Text(), nullable=True)
    genre: Mapped[str | None] = mapped_column(String(80), nullable=True)
    motif: Mapped[str | None] = mapped_column(Text(), nullable=True)
    motif_chapter: Mapped[str | None] = mapped_column(Text(), nullable=True)  # unread since Oct 4, kept on old rows
    politics: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    rumor_class: Mapped[str | None] = mapped_column(String(40), nullable=True)
    secret_plot: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    conspiracy: Mapped[str | None] = mapped_column(String(40), nullable=True)
    family: Mapped[str | None] = mapped_column(String(80), nullable=True)
    villain: Mapped[str | None] = mapped_column(Text(), nullable=True)
    victim: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model: Mapped[str | None] = mapped_column(String(40), nullable=True)
    read: Mapped[str | None] = mapped_column(String(8), nullable=True)  # 'piece' or 'feed': what the model read

    # The labels' keys as the callers know them (the JSON's), and the column each is kept in
    KEYS = {'claim from the piece': 'claim_from_piece'}
    FIELDS = ('claim', 'claim_from_piece', 'context', 'genre', 'motif', 'motif_chapter', 'politics', 'rumor_class',
              'secret_plot', 'conspiracy', 'family', 'villain', 'victim', 'model', 'read')

    def to_dict(self) -> dict:
        names = {v: k for k, v in self.KEYS.items()}
        return {names.get(f, f): getattr(self, f) for f in self.FIELDS if getattr(self, f) is not None}

    @classmethod
    def from_dict(cls, url: str, labels: dict) -> dict:
        """Every column of the row from a labels dict, so a merge replaces the row whole (keys it has no column
        for are dropped)"""
        row = {cls.KEYS.get(k, k): v for k, v in labels.items()}
        for f in ('politics', 'secret_plot'):
            if row.get(f) is not None:
                row[f] = bool(row[f])
        return {'url': url, **{f: row.get(f) for f in cls.FIELDS}, 'claim': row.get('claim') or ''}
