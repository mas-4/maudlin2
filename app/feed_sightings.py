"""First sightings from an outlet's RSS feed, read alongside its front page (Oct 28, Breitbart). Breitbart's late-night
posts sit low on its homepage, or reach it only the next morning, so about a fifth of its articles were first seen a
day after the date in their address and Breitbart looked late to stories. Its feed lists each post as it goes up.

A feed item is not a front-page headline: it has no position, and it never becomes a Headline, so stories, lean bars
and "on the front pages" counts stay front-page only. What the feed gives is the article's first sighting: when the
front page first lists an article the feed listed in an earlier run, the article's first_accessed is the feed's time.
The article's headlines keep their own times, from the front page."""
import html
from datetime import datetime as dt
from email.utils import parsedate_to_datetime

import pytz
from bs4 import BeautifulSoup as Soup

from app.models import Session, SqlLock, FeedSighting
from app.utils import get_logger

logger = get_logger(__name__)


def _utc(text: str | None) -> dt | None:
    """An RSS pubDate as naive UTC, or None"""
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is not None:
        when = when.astimezone(pytz.UTC).replace(tzinfo=None)
    return when


def parse(soup: Soup) -> list[tuple[str, str, dt | None]]:
    """(link, title, published) for each item of an RSS feed, in the feed's order"""
    items = []
    for item in soup.find_all('item'):
        link, title = item.find('link'), item.find('title')
        if link is None or title is None:
            continue
        url, text = link.get_text(strip=True), html.unescape(title.get_text(strip=True))
        if url and text:
            date = item.find('pubDate')
            items.append((url, text, _utc(date.get_text(strip=True)) if date is not None else None))
    return items


def record(agency_id: int, items: list[tuple[str, str, dt | None]], now: dt = None) -> int:
    """Save one run's feed items; returns how many were new"""
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    items = list({url: (url, title, published) for url, title, published in items}.values())  # once per url
    new = 0
    with Session() as s, SqlLock:
        rows = {r.url: r for r in s.query(FeedSighting).filter(
            FeedSighting.agency_id == agency_id, FeedSighting.url.in_([url for url, _, _ in items]))}
        for url, title, published in items:
            row = rows.get(url)
            if row is None:
                row = FeedSighting(agency_id=agency_id, url=url, title=title, published=published, first_seen=now)
                s.add(row)
                new += 1
            row.last_seen = now
        s.commit()
    return new


def first_seen(s, agency_id: int, url: str) -> dt | None:
    """When the outlet's feed first listed `url` (naive UTC), or None"""
    return s.query(FeedSighting.first_seen).filter_by(agency_id=agency_id, url=url).scalar()
