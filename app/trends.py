"""What's trending outside the press, to compare with what the press is covering:

- Bluesky: topics people are posting about (public api, no auth)
- Google: what people are searching for (public Trending Now RSS)
- Wikipedia: what people are reading up on (Wikimedia pageviews api; data CC0)
- Mastodon: links being shared on mastodon.social (public api)

Each source is fetched independently and failures are logged, never raised, so one outage can't take down a
scrape. Every trend carries a `match_text` the homepage uses to find the news story it's about."""
import hashlib
import re
from datetime import datetime as dt, timedelta as td
from collections.abc import Callable

import pytz
import requests as rq
from bs4 import BeautifulSoup as Soup

from app.models import Session, Trend, TrendSighting, SqlLock
from app.utils import Config, get_logger

logger = get_logger(__name__)

USER_AGENT = 'Maudlin Bot (https://maudlin.news)'
LIMIT = 10


def _get(url: str, **params) -> rq.Response:
    response = rq.get(url, params=params, timeout=Config.timeout, headers={'User-Agent': USER_AGENT})
    response.raise_for_status()
    return response


def _topic(source: str, key: str) -> str:
    topic = f'{source}:{key}'
    return topic if len(topic) <= 64 else f'{source}:{hashlib.sha1(key.encode()).hexdigest()}'


def bluesky_link(link: str | None) -> str | None:
    """A Bluesky trend's page: the API gives a path ('/profile/…/feed/…'), or now and then a whole URL"""
    if not link:
        return None
    link = link[len('https://bsky.app'):] if link.startswith('https://bsky.apphttps://') else link
    return link if link.startswith(('http://', 'https://')) else 'https://bsky.app' + link


def bluesky() -> list[dict]:
    trends = _get('https://public.api.bsky.app/xrpc/app.bsky.unspecced.getTrends', limit=LIMIT).json()['trends']
    return [{
        'topic': t['topic'],  # bluesky's ids predate the source prefix; kept so old rows keep matching
        'display_name': t['displayName'],
        'description': t.get('description'),
        'category': t.get('category'),
        'link': bluesky_link(t.get('link')),
        'status': t.get('status'),
        'post_count': t.get('postCount'),
        'started_at': t.get('startedAt'),
    } for t in trends]


def google() -> list[dict]:
    soup = Soup(_get('https://trends.google.com/trending/rss', geo='US').content, 'xml')
    trends = []
    for item in soup.find_all('item')[:LIMIT]:
        query = item.find('title').get_text(strip=True)
        news = item.find('news_item_title')
        news_url = item.find('news_item_url')
        traffic = item.find('approx_traffic')
        searches = re.sub(r'\D', '', traffic.get_text()) if traffic else ''
        trends.append({
            'topic': _topic('google', query.lower()),
            'display_name': query,
            'description': news.get_text(strip=True) if news else None,
            'link': f'https://trends.google.com/trends/explore?geo=US&q={rq.utils.quote(query)}',
            'post_count': int(searches) if searches else None,
            'category': news_url.get_text(strip=True) if news_url else None,
        })
    return trends


# Pages that are always among the most viewed and say nothing about the news
WIKIPEDIA_SKIP = re.compile(r'^(Main_Page|Special:|Wikipedia:|Portal:|File:|Help:|Talk:|Template:|Category:|User:)')


def wikipedia() -> list[dict]:
    # Daily totals are published a few hours after the UTC day ends, so this is yesterday's reading, or the day
    # before's while yesterday's isn't out yet (from 8 PM Eastern until a little after midnight)
    for back in (1, 2):
        day = (dt.now(pytz.UTC) - td(days=back)).strftime('%Y/%m/%d')
        try:
            articles = _get(f'https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{day}'
                            ).json()['items'][0]['articles']
            break
        except rq.HTTPError as e:
            if back == 2 or e.response is None or e.response.status_code != 404:
                raise
    trends = []
    for article in articles:
        if WIKIPEDIA_SKIP.match(article['article']):
            continue
        title = article['article'].replace('_', ' ')
        try:
            # safe='': the REST path needs a slash in a title (AC/DC) escaped as %2F
            summary = _get('https://en.wikipedia.org/api/rest_v1/page/summary/'
                           + rq.utils.quote(article['article'], safe='')).json()
            description = summary.get('description')
        except Exception:  # noqa: a missing summary just means less to match on
            description = None
        trends.append({
            'topic': _topic('wikipedia', article['article']),
            'display_name': title,
            'description': description,
            'link': f"https://en.wikipedia.org/wiki/{rq.utils.quote(article['article'])}",
            'post_count': article['views'],
        })
        if len(trends) == LIMIT:
            break
    return trends


def mastodon() -> list[dict]:
    links = _get('https://mastodon.social/api/v1/trends/links', limit=LIMIT).json()
    return [{
        'topic': _topic('mastodon', link['url']),
        'display_name': link['title'],
        'description': None,  # usually the publisher's boilerplate, which would only confuse matching
        'category': link.get('provider_name'),
        'link': link['url'],
        # people sharing it over the last two days
        'post_count': sum(int(day['accounts']) for day in link.get('history', [])[:2]),
    } for link in links]


SOURCES: dict[str, Callable[[], list[dict]]] = {
    'bluesky': bluesky,
    'google': google,
    'wikipedia': wikipedia,
    'mastodon': mastodon,
}


def fetch_trends():
    """Record what's trending on every source."""
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    for source, fetch in SOURCES.items():
        try:
            trends = fetch()
        except Exception as e:  # noqa
            logger.error("Failed to fetch %s trends: %s", source, e)
            continue
        with Session() as s, SqlLock:
            for rank, raw in enumerate(trends, start=1):
                trend = s.query(Trend).filter_by(topic=raw['topic']).first()
                if trend is None:
                    trend = Trend(topic=raw['topic'], source=source, first_accessed=now)
                    s.add(trend)
                for field in ('display_name', 'description', 'category', 'link', 'status', 'post_count'):
                    setattr(trend, field, raw.get(field))
                if raw.get('started_at'):
                    trend.started_at = dt.fromisoformat(raw['started_at']).astimezone(pytz.UTC).replace(tzinfo=None)
                trend.rank = rank
                trend.last_accessed = now
                s.flush()  # gives a new trend its id
                s.add(TrendSighting(trend_id=trend.id, seen_at=now, rank=rank, post_count=raw.get('post_count')))
            s.commit()
        logger.info("Recorded %d %s trends", len(trends), source)


def current_trends(source: str = 'bluesky') -> list[Trend]:
    """One source's trends from its most recent fetch, in its own order."""
    with Session() as s:
        latest = s.query(Trend.last_accessed).filter(Trend.source == source) \
            .order_by(Trend.last_accessed.desc()).first()
        if latest is None:
            return []
        trends = s.query(Trend).filter(Trend.source == source, Trend.last_accessed == latest[0]) \
            .order_by(Trend.rank).all()
        s.expunge_all()
        return trends


def match_text(trend: Trend) -> str:
    return f'{trend.display_name}. {trend.description or ""}'
