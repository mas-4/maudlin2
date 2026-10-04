"""Headline A/B tests (#119). Slate puts every wording it's testing into its front page (one is shown at random to
each reader), so each run records the wordings on each card; when only one is left, that's the winner. Which wordings
lose, and which win, is a record of what an outlet thinks gets read."""
from collections import defaultdict
from datetime import datetime as dt, timedelta as td

import pytz

from app.models import Session, SqlLock, HeadlineVariant, Agency
from app.utils import get_logger

logger = get_logger(__name__)

GONE = td(hours=6)  # an article off the front page this long with several wordings: the test ended unseen
WINDOW = td(days=14)


def _clean(text: str) -> str:
    return ' '.join(text.split())


def record(agency_id: int, cards: list[tuple[str, list[str], str]], now: dt = None):
    """Save one run's cards (url, every wording on it, the default wording). A card with one wording is saved only
    when its article was tested before: that's how a test ends."""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    cards = [(url, list(dict.fromkeys(_clean(t) for t in texts if _clean(t))), _clean(default))
             for url, texts, default in cards]
    with Session() as s, SqlLock:
        urls = [url for url, texts, _ in cards if texts]
        tracked = {u for (u,) in s.query(HeadlineVariant.url).filter(HeadlineVariant.url.in_(urls)).distinct()}
        for url, texts, default in cards:
            if len(texts) < 2 and url not in tracked:
                continue
            rows = {r.text: r for r in s.query(HeadlineVariant).filter_by(url=url)}
            for text in texts:
                row = rows.get(text)
                if row is None:
                    row = HeadlineVariant(agency_id=agency_id, url=url, text=text, first_seen=now)
                    s.add(row)
                row.last_seen = now
                row.is_default = text == default
        s.commit()


def tests(days: float = None, now: dt = None) -> list[dict]:
    """Recent tests, newest first: each article's wordings (with how long each was up) and its state: 'running',
    'won' (one wording left) or 'ended' (off the front page with several still in play)."""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    since = now - (td(days=days) if days else WINDOW)
    with Session() as s:
        rows = s.query(HeadlineVariant, Agency.name, Agency._bias).join(Agency, Agency.id == HeadlineVariant.agency_id) \
            .filter(HeadlineVariant.last_seen >= since).all()
        by_url = defaultdict(list)
        for row, agency, bias in rows:
            by_url[(row.url, agency, bias)].append(row)
    out = []
    for (url, agency, bias), variants in by_url.items():
        if len(variants) < 2:
            continue
        latest = max(v.last_seen for v in variants)
        live = [v for v in variants if v.last_seen == latest]
        state = 'won' if len(live) == 1 else 'ended' if now - latest > GONE else 'running'
        winner = live[0].text if state == 'won' else None
        ordered = sorted(variants, key=lambda v: (v.text != winner, -(v.last_seen - v.first_seen).total_seconds()))
        out.append({'url': url, 'agency': agency, 'bias': bias, 'state': state, 'winner': winner,
                    'started': min(v.first_seen for v in variants), 'latest': latest,
                    'variants': [{'text': v.text, 'default': bool(v.is_default), 'live': v in live,
                                  'won': v.text == winner, 'hours': (v.last_seen - v.first_seen).total_seconds() / 3600}
                                 for v in ordered]})
    out.sort(key=lambda t: (t['state'] != 'running', -t['latest'].timestamp()))
    return out
