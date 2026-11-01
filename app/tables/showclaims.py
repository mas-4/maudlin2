"""Tables for the showclaims group (see app/tables/__init__.py): the claims read from the shows' transcripts
(app/analysis/show_claims.py) and the Focus Group's (app/analysis/focus_group.py), what the shows retold, the
transcripts the shows publish themselves (app/sidefeeds.py) and the episodes whose claims were read again
(scripts/retranscribe.py). The readers keep their old shapes (episode url -> entry with its claims) through
load_episodes and save_episodes here."""
import datetime as dt

from sqlalchemy import ForeignKey, Index, String, delete, insert, select
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Date, DateTime, Integer, Text

from app.models import Base

SHOWS, FOCUS_GROUP = 'shows', 'focus group'  # ShowEpisode.reader: which reader read it


class ShowEpisode(Base):
    """An episode read for claims, part by part: `read` of its `chunks` parts done"""
    __tablename__ = 'show_episode'
    reader: Mapped[str] = mapped_column(String(20), primary_key=True)
    url: Mapped[str] = mapped_column(String(500), primary_key=True)
    source: Mapped[str | None] = mapped_column(String(50))  # the side feed's key (the Focus Group's has none)
    show: Mapped[str | None] = mapped_column(String(100))
    lean: Mapped[str | None] = mapped_column(String(20))
    title: Mapped[str | None] = mapped_column(Text)
    date: Mapped[dt.date | None] = mapped_column(Date, index=True)
    read: Mapped[int] = mapped_column(Integer, default=0)
    chunks: Mapped[int | None] = mapped_column(Integer)


class ShowClaim(Base):
    """A claim read from an episode's part; `why` set when a check dropped it (the entry's 'dropped' list)"""
    __tablename__ = 'show_claim'
    __table_args__ = (Index('ix_show_claim_episode', 'reader', 'url'),)
    id: Mapped[int] = mapped_column(primary_key=True)  # in reading order
    reader: Mapped[str] = mapped_column(String(20))
    url: Mapped[str] = mapped_column(String(500))
    claim: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text, default='')
    speaker: Mapped[str | None] = mapped_column(String(10))  # the shows' (show_claims.SPEAKERS)
    side: Mapped[str | None] = mapped_column(String(40))  # the Focus Group's voter ("Trump voter")
    at: Mapped[int | None] = mapped_column(Integer)  # seconds into the episode its part starts
    reread: Mapped[str | None] = mapped_column(String(10))  # added when the episode was read again (retranscribe.py)
    support: Mapped[str | None] = mapped_column(String(10))  # 'checked': the support check passed (Focus Group)
    why: Mapped[str | None] = mapped_column(Text)


class RetoldClaim(Base):
    """A claim told on two or more shows (show_claims.retold), as the last run kept it; id is its rank"""
    __tablename__ = 'retold_claim'
    id: Mapped[int] = mapped_column(primary_key=True)
    claim: Mapped[str] = mapped_column(Text)
    shows: Mapped[str] = mapped_column(Text)  # JSON list of show names
    tellings: Mapped[int] = mapped_column(Integer)
    leans: Mapped[str] = mapped_column(Text)  # JSON: lean -> tellings
    speakers: Mapped[str] = mapped_column(Text)  # JSON: speaker -> tellings
    date: Mapped[dt.date | None] = mapped_column(Date)
    ref: Mapped[str] = mapped_column(String(500))


class RetoldTelling(Base):
    """One telling of a retold claim"""
    __tablename__ = 'retold_telling'
    id: Mapped[int] = mapped_column(primary_key=True)
    retold_id: Mapped[int] = mapped_column(ForeignKey('retold_claim.id', ondelete='CASCADE'), index=True)
    show: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(String(500))
    at: Mapped[int | None] = mapped_column(Integer)
    speaker: Mapped[str | None] = mapped_column(String(10))
    claim: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text, default='')


class FeedTranscript(Base):
    """The transcript a show publishes for one of its items (sidefeeds.TRANSCRIPT_TYPES), seen in its feed"""
    __tablename__ = 'feed_transcript'
    item_url: Mapped[str] = mapped_column(String(500), primary_key=True)
    transcript_url: Mapped[str] = mapped_column(Text)
    seen: Mapped[dt.datetime] = mapped_column(DateTime, index=True)


class RetranscribedClaims(Base):
    """An episode whose claims were read again after it was transcribed again (scripts/retranscribe.py claims)"""
    __tablename__ = 'retranscribed_claims'
    url: Mapped[str] = mapped_column(String(500), primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime)
    found: Mapped[int] = mapped_column(Integer)
    added: Mapped[int] = mapped_column(Integer)


EPISODE_KEYS = ('source', 'show', 'lean', 'title', 'date', 'read', 'chunks')
CLAIM_KEYS = ('claim', 'quote', 'speaker', 'side', 'at', 'reread', 'support')


def _day(value) -> dt.date | None:
    return dt.date.fromisoformat(str(value)[:10]) if value else None


def load_episodes(reader: str, session=None) -> dict:
    """episode url -> {source, show, lean, title, date, read, chunks, claims: [...], dropped: [...]}, the shape the
    readers kept in their JSON files; a claim has only the keys it was given"""
    from app.models import Session
    own = session is None
    s = Session() if own else session
    try:
        store = {}
        for row in s.execute(select(*(getattr(ShowEpisode, k) for k in ('url',) + EPISODE_KEYS))
                             .where(ShowEpisode.reader == reader)):
            entry = {k: v for k, v in zip(EPISODE_KEYS, row[1:]) if v is not None or k in ('lean', 'title')}
            if entry.get('date'):
                entry['date'] = entry['date'].isoformat()
            if reader == FOCUS_GROUP:  # never had these
                for k in ('source', 'show', 'lean'):
                    entry.pop(k, None)
            store[row[0]] = entry | {'claims': [], 'dropped': []}
        for row in s.execute(select(ShowClaim.url, ShowClaim.why, *(getattr(ShowClaim, k) for k in CLAIM_KEYS))
                             .where(ShowClaim.reader == reader).order_by(ShowClaim.id)):
            if row[0] not in store:
                continue
            c = {k: v for k, v in zip(CLAIM_KEYS, row[2:]) if v is not None or k in ('claim', 'quote')}
            if row[1] is None:
                store[row[0]]['claims'].append(c)
            else:
                store[row[0]]['dropped'].append(c | {'why': row[1]})
        return store
    finally:
        if own:
            s.close()


def save_episodes(reader: str, store: dict, urls=None, session=None):
    """Write these episodes of `store` (all of them when urls is None), each replacing what was kept for it, in one
    transaction (or in `session`'s, uncommitted)"""
    from app.models import Session
    urls = list(store) if urls is None else [u for u in dict.fromkeys(urls) if u in store]
    if not urls:
        return
    own = session is None
    s = Session() if own else session
    try:
        for start in range(0, len(urls), 500):  # SQLite's limit on bound parameters
            part = urls[start:start + 500]
            s.execute(delete(ShowClaim).where(ShowClaim.reader == reader, ShowClaim.url.in_(part)))
            s.execute(delete(ShowEpisode).where(ShowEpisode.reader == reader, ShowEpisode.url.in_(part)))
        episodes, claims = [], []
        for url in urls:
            e = store[url]
            episodes.append({'reader': reader, 'url': url, **{k: e.get(k) for k in EPISODE_KEYS},
                             'date': _day(e.get('date')), 'read': e.get('read', 0)})
            for why, items in ((False, e.get('claims', [])), (True, e.get('dropped', []))):
                for c in items:
                    claims.append({'reader': reader, 'url': url, **{k: c.get(k) for k in CLAIM_KEYS},
                                   'quote': c.get('quote') or '', 'why': (c.get('why') or '?') if why else None})
        s.execute(insert(ShowEpisode), episodes)
        if claims:
            s.execute(insert(ShowClaim), claims)
        if own:
            s.commit()
    finally:
        if own:
            s.close()


def load_retold(session=None) -> list[dict]:
    """The retold claims in rank order, each with its tellings ('told'), as show_claims.retold() gives them"""
    import json
    from app.models import Session
    own = session is None
    s = Session() if own else session
    try:
        told = {}
        for t in s.execute(select(RetoldTelling).order_by(RetoldTelling.id)).scalars():
            told.setdefault(t.retold_id, []).append({'show': t.show, 'url': t.url, 'at': t.at, 'speaker': t.speaker,
                                                      'claim': t.claim, 'quote': t.quote})
        return [{'claim': r.claim, 'shows': json.loads(r.shows), 'tellings': r.tellings, 'leans': json.loads(r.leans),
                 'speakers': json.loads(r.speakers), 'date': r.date.isoformat() if r.date else None, 'ref': r.ref,
                 'told': told.get(r.id, [])}
                for r in s.execute(select(RetoldClaim).order_by(RetoldClaim.id)).scalars()]
    finally:
        if own:
            s.close()


def save_retold(groups: list[dict], session=None):
    """Replace the retold claims with these, in their order"""
    import json
    from app.models import Session
    own = session is None
    s = Session() if own else session
    try:
        s.execute(delete(RetoldTelling))
        s.execute(delete(RetoldClaim))
        rows, tellings = [], []
        for n, g in enumerate(groups, 1):
            rows.append({'id': n, 'claim': g['claim'], 'shows': json.dumps(g.get('shows', [])),
                         'tellings': g.get('tellings', len(g.get('told', []))), 'leans': json.dumps(g.get('leans', {})),
                         'speakers': json.dumps(g.get('speakers', {})), 'date': _day(g.get('date')), 'ref': g.get('ref', '')})
            tellings += [{'retold_id': n, 'show': t.get('show', ''), 'url': t.get('url', ''), 'at': t.get('at'),
                          'speaker': t.get('speaker'), 'claim': t.get('claim', ''), 'quote': t.get('quote') or ''}
                         for t in g.get('told', [])]
        if rows:
            s.execute(insert(RetoldClaim), rows)
        if tellings:
            s.execute(insert(RetoldTelling), tellings)
        if own:
            s.commit()
    finally:
        if own:
            s.close()


def any_retold() -> bool:
    from app.models import Session
    with Session() as s:
        return s.execute(select(RetoldClaim.id).limit(1)).first() is not None
