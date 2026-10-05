"""Investigations: open-source and investigative outfits (Bellingcat, ICIJ, OCCRP, DFRLab, Citizen Lab, Just Security)
that publish a few deep pieces a week rather than a front page. They're kept apart from the outlets: their pieces
don't count toward stories, the word cloud or any lean or mood measure. The homepage lists the newest ones and points
to the current story each is about, when there is one.

Polite by design: each feed is read once per run (hourly), with conditional requests (ETag / Last-Modified) so an
unchanged feed sends nothing back, and only headlines, links and the feed's own short summaries are kept. Results are
cached in data/investigations.json; a source that errors keeps its last good items."""
import html
import os
import re
from datetime import datetime as dt, timedelta as td
from email.utils import parsedate_to_datetime
from typing import Optional

import pytz
import requests as rq
from bs4 import BeautifulSoup as Soup

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

CACHE = os.path.join(Config.data, 'investigations.json')
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
KEEP = 20  # newest items kept per source
# Each outfit's chip on the front page: a short name, an emoji for what it does, a color, and a one-line description
SOURCES = [
    {'key': 'bellingcat', 'name': 'Bellingcat', 'short': 'Bellingcat', 'emoji': '🛰️', 'color': '#ff6b1a',
     'about': 'Open-source investigations from satellite images, video and social media',
     'home': 'https://www.bellingcat.com/', 'feed': 'https://www.bellingcat.com/feed/'},
    {'key': 'icij', 'name': 'ICIJ', 'short': 'ICIJ', 'emoji': '🌐', 'color': '#3a86ff',
     'about': 'International Consortium of Investigative Journalists: cross-border leaks like the Panama Papers',
     'home': 'https://www.icij.org/', 'feed': 'https://www.icij.org/feed/'},
    {'key': 'occrp', 'name': 'OCCRP', 'short': 'OCCRP', 'emoji': '🕵️', 'color': '#8a5cff',
     'about': 'Organized Crime and Corruption Reporting Project',
     'home': 'https://www.occrp.org/en', 'feed': 'https://www.occrp.org/en/feed'},
    {'key': 'dfrlab', 'name': 'DFRLab', 'short': 'DFRLab', 'emoji': '🧪', 'color': '#00c2a8',
     'about': "The Atlantic Council's Digital Forensic Research Lab: disinformation and influence operations",
     'home': 'https://dfrlab.org/', 'feed': 'https://dfrlab.org/feed/'},
    {'key': 'citizenlab', 'name': 'Citizen Lab', 'short': 'Citizen Lab', 'emoji': '🔐', 'color': '#ff4fa3',
     'about': 'University of Toronto lab tracking spyware and digital threats to civil society',
     'home': 'https://citizenlab.ca/', 'feed': 'https://citizenlab.ca/feed/'},
    {'key': 'justsecurity', 'name': 'Just Security', 'short': 'Just Security', 'emoji': '⚖️', 'color': '#ffc400',
     'about': 'National security law and policy, from NYU Law',
     'home': 'https://www.justsecurity.org/', 'feed': 'https://www.justsecurity.org/feed/'},
]


def _date(text: Optional[str]) -> Optional[str]:
    """RSS (RFC 822) or Atom (ISO 8601) dates as UTC ISO strings."""
    if not text:
        return None
    text = text.strip()
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            when = dt.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=pytz.UTC)
    return when.astimezone(pytz.UTC).isoformat()


def _summary(text: Optional[str], limit: int = 280) -> str:
    plain = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', text or ''))).strip()
    return plain if len(plain) <= limit else plain[:limit].rsplit(' ', 1)[0] + '…'


def parse(xml: str) -> list[dict]:
    soup = Soup(xml, 'xml')
    items = []
    for item in soup.find_all(['item', 'entry'])[:KEEP]:
        title, link = item.find('title'), item.find('link')
        if title is None or link is None:
            continue
        href = link.get('href') or link.get_text(strip=True)
        when = item.find(['pubDate', 'published', 'updated'])
        summary = item.find(['description', 'summary'])
        items.append({'title': html.unescape(title.get_text(strip=True)), 'url': href,
                      'published': _date(when.get_text() if when else None),
                      'summary': _summary(summary.get_text() if summary else '')})
    return items


def _load() -> dict:
    return read_json(CACHE, {})


def fetch_investigations():
    """Read each source's feed once, keeping its last good items when it fails or hasn't changed."""
    cache = _load()
    for source in SOURCES:
        entry = cache.get(source['key'], {})
        headers = {'User-Agent': USER_AGENT}
        if entry.get('etag'):
            headers['If-None-Match'] = entry['etag']
        if entry.get('modified'):
            headers['If-Modified-Since'] = entry['modified']
        try:
            response = rq.get(source['feed'], headers=headers, timeout=Config.timeout)
            if response.status_code == 304:
                continue
            response.raise_for_status()
            items = parse(response.text)
        except Exception as e:  # noqa: one source failing mustn't stop the run
            logger.warning("Investigations: %s failed (%s); keeping its last items", source['name'], e)
            continue
        cache[source['key']] = {'items': items, 'etag': response.headers.get('ETag'),
                                'modified': response.headers.get('Last-Modified'),
                                'fetched': dt.now(pytz.UTC).isoformat()}
    write_json(CACHE, cache)
    logger.info("Investigations: %d items from %d sources", sum(len(v.get('items', [])) for v in cache.values()),
                len(cache))


def recent(days: int = 14, limit: int = 8, per_source: int = 2) -> list[dict]:
    """The newest pieces across sources, newest first, at most `per_source` each so one busy source can't fill it."""
    cache = _load()
    since = dt.now(pytz.UTC) - td(days=days)
    pieces = []
    for source in SOURCES:
        # Its two newest in the window, whatever order the feed lists them in
        fresh = [i for i in cache.get(source['key'], {}).get('items', [])
                 if i.get('published') and dt.fromisoformat(i['published']) >= since]
        fresh.sort(key=lambda i: dt.fromisoformat(i['published']), reverse=True)
        pieces += [{**item, 'source': source['name'], 'home': source['home'], 'short': source['short'],
                    'emoji': source['emoji'], 'color': source['color'], 'about': source['about']}
                   for item in fresh[:per_source]]
    pieces.sort(key=lambda p: dt.fromisoformat(p['published']), reverse=True)
    return pieces[:limit]
