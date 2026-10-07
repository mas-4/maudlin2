"""Trend arrows on story cards (#133): each run saves every story's meters (story_snapshot); a card's arrows show how
far its lean and mood have moved over the last TREND_HOURS, more arrows for more movement. Lean arrows point the way
coverage is shifting (◀ more left-leaning outlets, ▶ more right); mood arrows ▲ brighter, ▼ grimmer."""
from datetime import datetime as dt, timedelta as td

import pytz

from app.models import Session, SqlLock, StorySnapshot
from app.utils import get_logger

logger = get_logger(__name__)

TREND_HOURS = 6  # compare now with the oldest snapshot this recent...
MIN_HOURS = 2  # ...if it's at least this old
# Change over the window for one, two or three arrows
LEAN_STEPS = (0.15, 0.35, 0.6)  # lean, relative to the day's outlets (about -2 to 2)
MOOD_STEPS = (0.1, 0.25, 0.45)  # mood, -1 grim to 1 upbeat


def save(meters: dict[int, dict], now: dt | None = None):
    """meters: story id -> {'lean', 'mood', 'outlets'}, one row each for this run."""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    with Session() as s, SqlLock:
        s.add_all([StorySnapshot(story_id=sid, at=now, lean=float(m['lean']), mood=float(m['mood']),
                                 outlets=int(m['outlets'])) for sid, m in meters.items()])
        s.commit()


def arrows(change: float, steps: tuple, up: str, down: str) -> str:
    n = sum(abs(change) >= step for step in steps)
    return (up if change > 0 else down) * n


def trends(story_ids: list[int], now: dt | None = None) -> dict[int, dict]:
    """story id -> {'lean': {'arrows', 'tip'}, 'mood': {...}} for stories with at least MIN_HOURS of history."""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    since = now - td(hours=TREND_HOURS)
    with Session() as s:
        rows = s.query(StorySnapshot).filter(StorySnapshot.story_id.in_(story_ids), StorySnapshot.at >= since) \
            .order_by(StorySnapshot.at).all()
        s.expunge_all()
    by_story = {}
    for row in rows:
        by_story.setdefault(row.story_id, []).append(row)
    out = {}
    for sid, snaps in by_story.items():
        first, last = snaps[0], snaps[-1]
        hours = (last.at - first.at).total_seconds() / 3600
        if hours < MIN_HOURS:
            continue
        span = f'over {hours:.0f} hours'
        out[sid] = {
            'lean': {'arrows': arrows(last.lean - first.lean, LEAN_STEPS, '▶', '◀'),
                     'tip': f'lean {first.lean:+.2f} → {last.lean:+.2f} {span} (outlets {first.outlets} → {last.outlets})'},
            'mood': {'arrows': arrows(last.mood - first.mood, MOOD_STEPS, '▲', '▼'),
                     'tip': f'mood {first.mood:+.2f} → {last.mood:+.2f} {span}'},
        }
    return out
