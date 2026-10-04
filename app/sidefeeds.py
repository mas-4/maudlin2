"""Newsletters, podcasts and political video channels, collected into the database for the long run (side_item) and,
for the news-of-the-day ones, shown on the front page.

Sources are classified by how they relate to the news cycle, not by format (#135): news-of-the-day sources react to
this week's news, several stories at a time (Pod Save America, Breaking Points, Up First); thinking sources take one
subject at a time, often not tied to the week (The Remnant, Noahpinion). Only `publish` sources appear on the site;
everything is archived.

Polite by design: each feed is read at most every REFRESH, with conditional requests (ETag / Last-Modified, so an
unchanged feed sends nothing back), requests to the same host a few seconds apart, and only the newest items parsed.
A feed that fails just waits for its next turn."""
import json
import os
import time
from collections import defaultdict
from datetime import datetime as dt, timedelta as td
from typing import Optional
from urllib.parse import urlparse

import pytz
import requests as rq
from bs4 import BeautifulSoup as Soup
from sqlalchemy.exc import IntegrityError

from app.investigations import _date, _summary
from app.models import Session, SqlLock, SideItem
from app.utils import Config, get_logger

logger = get_logger(__name__)

STATE = os.path.join(Config.data, 'sidefeeds_state.json')  # ETag / Last-Modified / last fetch per source
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
REFRESH = td(hours=2)
HOST_PAUSE = 5  # seconds between requests to one host (several shows share megaphone, substack, youtube)
NEWEST = 40  # items parsed per feed (some podcast feeds hold thousands)
YOUTUBE = 'https://www.youtube.com/feeds/videos.xml?channel_id='


def _source(key, name, kind, group, url, publish=False, refresh=None):
    return {'key': key, 'name': name, 'kind': kind, 'group': group, 'url': url, 'publish': publish,
            'refresh': refresh or REFRESH}


# kind: newsletter, podcast or video. group: left, right, center or crossover (a loose lean by reputation, for
# balance and colors; AllSides ratings, where they exist, stay in ratings.csv). publish: news of the day, shown on site
SOURCES = [
    # News of the day (published)
    _source('psa', 'Pod Save America', 'podcast', 'left', 'https://audioboom.com/channels/5166624.rss', True),
    _source('bulwarkpod', 'The Bulwark Podcast', 'podcast', 'left', 'https://audioboom.com/channels/5114286.rss', True),
    _source('hacks', 'Hacks on Tap', 'podcast', 'left', 'https://feeds.megaphone.fm/VMP7545057845', True),
    _source('hcr', 'Letters from an American', 'newsletter', 'left', 'https://heathercoxrichardson.substack.com/feed', True),
    _source('popinfo', 'Popular Information', 'newsletter', 'left', 'https://popular.info/feed', True),
    _source('downballot', 'The Downballot', 'newsletter', 'left', 'https://www.the-downballot.com/feed', True),
    _source('breakingpoints', 'Breaking Points', 'podcast', 'center',
            'https://www.omnycontent.com/d/playlist/e73c998e-6e60-432f-8610-ae210140c5b1/'
            'e7fd5ae7-7621-4e41-9b85-b0ab0164b634/4c1a5135-4197-47c9-b19b-b0ab0164b667/podcast.rss', True),
    _source('upfirst', 'Up First (NPR)', 'podcast', 'center', 'https://feeds.npr.org/510318/podcast.xml', True),
    _source('nprpolitics', 'NPR Politics Podcast', 'podcast', 'center', 'https://feeds.npr.org/510310/podcast.xml', True),
    _source('ruthless', 'Ruthless', 'podcast', 'right', 'https://feeds.megaphone.fm/FOXM5875505224', True),
    _source('megyn', 'The Megyn Kelly Show', 'podcast', 'right', 'https://feeds.simplecast.com/RV1USAfC', True),
    _source('erickson', 'Erick Erickson', 'newsletter', 'right', 'https://ewerickson.substack.com/feed', True),
    _source('foxrundown', 'Fox News Rundown', 'podcast', 'right', 'https://feeds.megaphone.fm/FOXM1880458659', True),
    _source('yt_hasan', 'Hasan Piker', 'video', 'left', YOUTUBE + 'UCnI_h3e6b5jGLfly2SY57SA', True),
    _source('yt_destiny', 'Destiny', 'video', 'left', YOUTUBE + 'UCLOPC6bOBuiSBAJ16JXLAHg', True),
    _source('yt_vaush', 'Vaush', 'video', 'left', YOUTUBE + 'UCdUD6racxisHiSX9iWFcuug', True),
    _source('yt_majority', 'The Majority Report', 'video', 'left', YOUTUBE + 'UC-3jIAlnQmbbVMV6gR7K8aQ', True),
    # Archived for research
    _source('remnant', 'The Remnant', 'podcast', 'right', 'https://feeds.megaphone.fm/DISPME4897766830'),
    _source('daily', 'The Daily (NYT)', 'podcast', 'center', 'https://feeds.simplecast.com/Sl5CSM3S'),
    _source('todayexplained', 'Today, Explained', 'podcast', 'left', 'https://feeds.megaphone.fm/VMP5705694065'),
    _source('dispatchpod', 'The Dispatch Podcast', 'podcast', 'right', 'https://feeds.megaphone.fm/DISPME9513417677'),
    _source('advisory', 'Advisory Opinions', 'podcast', 'right', 'https://feeds.megaphone.fm/DISPME4573820108'),
    _source('strict', 'Strict Scrutiny', 'podcast', 'left', 'https://audioboom.com/channels/5166629.rss'),
    _source('tucker', 'The Tucker Carlson Show', 'podcast', 'right', 'https://feeds.megaphone.fm/RSV1597324942'),
    _source('warroom', "Bannon's War Room", 'podcast', 'right', 'https://listen.warroom.org/feed.xml'),
    _source('kye', 'Know Your Enemy', 'podcast', 'left', 'https://feeds.simplecast.com/MQHnVVgK'),
    _source('lrc', 'Left, Right & Center', 'podcast', 'center', 'https://leftrightandcenter-feed.kcrw.com'),
    _source('krugman', 'Paul Krugman', 'newsletter', 'left', 'https://paulkrugman.substack.com/feed'),
    _source('silver', 'Silver Bulletin', 'newsletter', 'center', 'https://www.natesilver.net/feed'),
    _source('slowboring', 'Slow Boring', 'newsletter', 'center', 'https://www.slowboring.com/feed'),
    _source('noahpinion', 'Noahpinion', 'newsletter', 'center', 'https://www.noahpinion.blog/feed'),
    _source('persuasion', 'Persuasion', 'newsletter', 'center', 'https://www.persuasion.community/feed'),
    _source('tangle', 'Tangle', 'newsletter', 'center', 'https://www.readtangle.com/feed'),
    _source('dish', 'The Weekly Dish', 'newsletter', 'center', 'https://andrewsullivan.substack.com/feed'),
    _source('racket', 'Racket News', 'newsletter', 'crossover', 'https://www.racket.news/feed'),
    _source('fp', 'The Free Press', 'newsletter', 'right', 'https://www.thefp.com/feed'),
    _source('hanania', 'Richard Hanania', 'newsletter', 'right', 'https://www.richardhanania.com/feed'),
    _source('rufo', 'Christopher F. Rufo', 'newsletter', 'right', 'https://christopherrufo.com/feed'),
    _source('argument', 'The Argument', 'newsletter', 'left', 'https://www.theargumentmag.com/feed'),
    _source('steady', 'Steady (Dan Rather)', 'newsletter', 'left', 'https://steady.substack.com/feed'),
    # NPR's 5-minute newscast at the top of every hour: titles are only timestamps and the feed holds the last four,
    # so it's read hourly and archived (its audio links) for transcription later, not shown
    _source('nprnewsnow', 'NPR News Now', 'podcast', 'center', 'https://feeds.npr.org/500005/podcast.xml',
            refresh=td(minutes=55)),
]
BY_KEY = {s['key']: s for s in SOURCES}


def parse(xml: str) -> list[dict]:
    """The newest items of an RSS or Atom feed (podcast and YouTube feeds included): title, url, published, summary."""
    soup = Soup(xml, 'xml')
    items = []
    for item in soup.find_all(['item', 'entry'])[:NEWEST]:
        title = item.find('title')
        link = item.find('link')
        url = (link.get('href') or link.get_text(strip=True)) if link is not None else None
        if not url:  # podcast items without a link: their guid or audio file still identifies them
            guid, enclosure = item.find('guid'), item.find('enclosure')
            url = (guid.get_text(strip=True) if guid is not None else None) or \
                  (enclosure.get('url') if enclosure is not None else None)
        when = item.find(['pubDate', 'published', 'updated'])
        summary = item.find(['description', 'summary']) or item.find('media:description')
        if title is None or not url:
            continue
        enclosure = item.find('enclosure')
        audio = enclosure.get('url') if enclosure is not None and 'audio' in (enclosure.get('type') or 'audio') else None
        items.append({'title': title.get_text(strip=True), 'url': url[:500], 'audio': (audio or '')[:500] or None,
                      'published': _date(when.get_text() if when else None),
                      'summary': _summary(summary.get_text() if summary else '', 400)})
    return items


def _load_state() -> dict:
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save(source: str, items: list[dict], now: dt) -> int:
    """Store new items (one row per source and url, never overwritten); returns how many were new."""
    new = 0
    with Session() as s, SqlLock:
        known = {u for (u,) in s.query(SideItem.url).filter(SideItem.source == source)}
        for item in items:
            if item['url'] in known:
                continue
            published = dt.fromisoformat(item['published']).replace(tzinfo=None) if item['published'] else None
            s.add(SideItem(source=source, title=item['title'][:500], url=item['url'], published=published,
                           summary=item['summary'], audio=item.get('audio'), first_seen=now))
            known.add(item['url'])
            new += 1
        try:
            s.commit()
        except IntegrityError:  # another run stored them first
            s.rollback()
            return 0
    return new


def fetch_sidefeeds(force: bool = False):
    """Read every source that's due, host by host with a pause between requests to the same host."""
    state = _load_state()
    now = dt.now(pytz.UTC)
    due = [src for src in SOURCES if force or not state.get(src['key'], {}).get('fetched')
           or now - dt.fromisoformat(state[src['key']]['fetched']) >= src['refresh']]
    by_host = defaultdict(list)
    for src in due:
        by_host['.'.join(urlparse(src['url']).hostname.split('.')[-2:])].append(src)
    total = 0
    for host_sources in by_host.values():
        for i, src in enumerate(host_sources):
            if i:
                time.sleep(HOST_PAUSE)
            entry = state.get(src['key'], {})
            headers = {'User-Agent': USER_AGENT}
            if entry.get('etag'):
                headers['If-None-Match'] = entry['etag']
            if entry.get('modified'):
                headers['If-Modified-Since'] = entry['modified']
            try:
                response = rq.get(src['url'], headers=headers, timeout=Config.timeout)
                if response.status_code != 304:
                    response.raise_for_status()
                    total += save(src['key'], parse(response.text), now.replace(tzinfo=None))
                    entry = {'etag': response.headers.get('ETag'), 'modified': response.headers.get('Last-Modified')}
            except Exception as e:  # noqa: one source failing mustn't stop the run; it waits for its next turn
                logger.warning("Side feeds: %s failed (%s)", src['name'], e)
            entry['fetched'] = now.isoformat()
            state[src['key']] = entry
    with open(STATE, 'w') as f:
        json.dump(state, f)
    logger.info("Side feeds: read %d sources, %d new items", len(due), total)


def recent(days: int = 3, limit: int = 12, per_source: int = 1) -> list[dict]:
    """The newest items from published sources, newest first, at most `per_source` each."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=days)
    published = [s['key'] for s in SOURCES if s['publish']]
    with Session() as s:
        rows = s.query(SideItem).filter(SideItem.source.in_(published), SideItem.published >= since) \
            .order_by(SideItem.published.desc()).all()
        s.expunge_all()
    picked, counts = [], defaultdict(int)
    for row in rows:
        if counts[row.source] >= per_source:
            continue
        counts[row.source] += 1
        src = BY_KEY[row.source]
        picked.append({'title': row.title, 'url': row.url, 'summary': row.summary or '',
                       'published': row.published.replace(tzinfo=pytz.UTC).isoformat(),
                       'source': src['name'], 'kind': src['kind'], 'group': src['group']})
        if len(picked) == limit:
            break
    return picked


def source_for(key: str) -> Optional[dict]:
    return BY_KEY.get(key)
