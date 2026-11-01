"""A few of a narrative's own posts, shown on the site: only ones that were already widely seen, and only embedded from
Bluesky itself, so a post its author deletes disappears from our pages too.

The nightly narrative report keeps, for each narrative, the addresses of its Bluesky posts that tell its claim most
closely (app/narratives.py, URI_CANDIDATES). Here those posts are looked up on Bluesky's public API (no account; a
few calls a run, spaced out): their likes, reposts, quotes and replies, and their author's follower count and labels.
A post is shown when it was widely seen (MIN_INTERACTIONS, or an account with MIN_FOLLOWERS), its author hasn't asked
Bluesky not to show their posts to logged-out visitors (the "!no-unauthenticated" label), and neither it nor its
author carries a moderation label. Bluesky gives no view counts. Shown posts are looked up again each run, oldest
check first, so one deleted or hidden since drops off.

Mastodon posts are never shown: their authors opted in to search, not to being republished."""
import time
from datetime import datetime as dt, timedelta as td, UTC

from app.utils import get_logger

logger = get_logger(__name__)

API = 'https://public.api.bsky.app/xrpc/'
MIN_INTERACTIONS = 25  # likes, reposts, quotes and replies together
MIN_FOLLOWERS = 5000  # ...or posted by an account this big (with some interaction)
MIN_BIG_ACCOUNT = 3
SHOWN = 2  # posts shown with each narrative, at most
CALLS = 8  # API calls a run, at most (25 posts or 25 profiles each)
GAP = 10  # seconds between calls
RECHECK = td(hours=6)  # a post shown on the site is looked up again after this long
FRESH = td(days=2)  # a post's counts settle within a day or two: one not shown is looked up again until then
KEEP = td(days=30)  # the same as the posts themselves (app/vernacular.py)
HIDE = {'!no-unauthenticated', '!hide', '!warn', 'bot', 'porn', 'sexual', 'nudity', 'graphic-media', 'gore', 'spam'}


def now() -> dt:
    return dt.now(UTC).replace(tzinfo=None)


def interactions(p: dict) -> int:
    return sum(p.get(k) or 0 for k in ('likes', 'reposts', 'quotes', 'replies'))


def showable(p: dict) -> bool:
    if not p or p.get('gone') or p.get('hidden') or 'likes' not in p:
        return False
    n = interactions(p)
    return n >= MIN_INTERACTIONS or ((p.get('followers') or 0) >= MIN_FOLLOWERS and n >= MIN_BIG_ACCOUNT)


def examples(uris: list[str], cache: dict | None = None) -> list[dict]:
    """The posts to show with a narrative, most interaction first: {uri, cid, url, handle, likes, reposts, ...}"""
    cache = load() if cache is None else cache
    found = [dict(cache[u], uri=u) for u in uris or [] if showable(cache.get(u))]
    found.sort(key=lambda p: -interactions(p))
    for p in found:
        did, rkey = p['uri'][len('at://'):].split('/app.bsky.feed.post/')
        p['url'] = f'https://bsky.app/profile/{did}/post/{rkey}'
    return found[:SHOWN]


def _get(method: str, key: str, values: list[str]) -> dict:
    import requests
    r = requests.get(API + method, params=[(key, v) for v in values], timeout=20,
                     headers={'User-Agent': 'bignews.day (research; https://bignews.day)'})
    r.raise_for_status()
    return r.json()


def refresh(uris: list[str], calls: int = CALLS, get=_get, sleep=time.sleep) -> dict:
    """Look up the posts that need it, at most `calls` API calls: first ones shown on the site whose last check is
    RECHECK old (oldest first), then ones never looked up, then young ones not shown yet whose counts may have grown.
    `uris`: every candidate, the newest narratives' first."""
    cache = load()
    t = now()
    stamp = lambda p: dt.fromisoformat(p['checked'])  # noqa: E731
    shown = sorted((u for u in uris if showable(cache.get(u)) and t - stamp(cache[u]) >= RECHECK),
                   key=lambda u: stamp(cache[u]))
    new = [u for u in uris if u not in cache]
    young = [u for u in uris if u in cache and not cache[u].get('gone') and not showable(cache[u])
             and t - dt.fromisoformat(cache[u].get('first', cache[u]['checked'])) < FRESH
             and t - stamp(cache[u]) >= RECHECK]
    todo = list(dict.fromkeys(shown + new + young))
    used = 0
    while todo and used < calls:
        batch, todo = todo[:25], todo[25:]
        if used:
            sleep(GAP)
        try:
            posts = {p['uri']: p for p in _posts(get, batch)}
        except Exception as e:  # noqa: BLE001 - Bluesky down: what we had stands
            logger.warning("Bluesky examples: lookup failed (%s)", e)
            break
        used += 1
        stamp_now = t.isoformat(timespec='seconds')
        for u in batch:
            p = posts.get(u)
            before = cache.get(u, {})
            if p is None:  # deleted, or hidden by its author or by Bluesky: never shown again
                cache[u] = {'gone': True, 'checked': stamp_now, 'first': before.get('first', stamp_now)}
                continue
            author = p.get('author') or {}
            labels = {x.get('val') for x in (p.get('labels') or []) + (author.get('labels') or [])}
            cache[u] = {**before, 'cid': p.get('cid'), 'did': author.get('did'), 'handle': author.get('handle'),
                        'likes': p.get('likeCount', 0), 'reposts': p.get('repostCount', 0),
                        'quotes': p.get('quoteCount', 0), 'replies': p.get('replyCount', 0),
                        'hidden': bool(labels & HIDE), 'checked': stamp_now, 'first': before.get('first', stamp_now)}
        # Follower counts for authors whose post might be shown on them (some interaction, not enough on its own)
        need = sorted({cache[u]['did'] for u in batch if cache.get(u, {}).get('did') and not cache[u].get('hidden')
                       and MIN_BIG_ACCOUNT <= interactions(cache[u]) < MIN_INTERACTIONS
                       and 'followers' not in cache[u]})
        if need and used < calls:
            sleep(GAP)
            try:
                profiles = {p['did']: p for p in get('app.bsky.actor.getProfiles', 'actors', need[:25]).get('profiles', [])}
                used += 1
            except Exception as e:  # noqa
                logger.warning("Bluesky examples: profiles failed (%s)", e)
                profiles = {}
            for u in batch:
                prof = profiles.get(cache.get(u, {}).get('did'))
                if prof:
                    cache[u]['followers'] = prof.get('followersCount', 0)
                    if {x.get('val') for x in prof.get('labels') or []} & HIDE:
                        cache[u]['hidden'] = True
    cutoff = t - KEEP
    cache = {u: p for u, p in cache.items() if dt.fromisoformat(p.get('first', p['checked'])) >= cutoff}
    save(cache, cutoff)
    logger.info("Bluesky examples: %d calls, %d posts known, %d showable, %d left to look up", used, len(cache),
                sum(showable(p) for p in cache.values()), len(todo))
    return cache


# A post's row as the dict the rest of this module works on (the shape the JSON file had): no keys for what Bluesky
# never said, times as ISO text
FIELDS = ('cid', 'did', 'handle', 'likes', 'reposts', 'quotes', 'replies', 'followers')


def as_dict(r) -> dict:
    if r.gone:
        return {'gone': True, 'checked': r.checked.isoformat(timespec='seconds'),
                'first': r.first.isoformat(timespec='seconds')}
    p = {k: getattr(r, k) for k in FIELDS if getattr(r, k) is not None or k in ('cid', 'did', 'handle')}
    if r.likes is None:  # never answered for: no counts, as before
        p = {k: v for k, v in p.items() if k not in ('likes', 'reposts', 'quotes', 'replies')}
    return {**p, 'hidden': bool(r.hidden), 'checked': r.checked.isoformat(timespec='seconds'),
            'first': r.first.isoformat(timespec='seconds')}


def as_row(uri: str, p: dict) -> dict:
    checked = dt.fromisoformat(p['checked'])
    return {'uri': uri, **{k: p.get(k) for k in FIELDS}, 'hidden': bool(p.get('hidden')), 'gone': bool(p.get('gone')),
            'checked': checked, 'first': dt.fromisoformat(p['first']) if p.get('first') else checked}


def load() -> dict:
    """Every post looked up: address -> what Bluesky said about it, and when"""
    from app.models import Session
    from app.tables.records import BlueskyPost
    with Session() as s:
        return {r.uri: as_dict(r) for r in s.query(BlueskyPost)}


def save(cache: dict, cutoff: dt):
    """The posts as they now stand, in one transaction: rows changed or new written, ones first seen before cutoff
    dropped"""
    from app.models import Session
    from app.tables.records import BlueskyPost
    with Session() as s:
        before = {r.uri: as_dict(r) for r in s.query(BlueskyPost)}
        s.query(BlueskyPost).filter(BlueskyPost.first < cutoff).delete(synchronize_session=False)
        changed = [as_row(u, p) for u, p in cache.items() if before.get(u) != p]
        for i in range(0, len(changed), 500):  # under SQLite's limit on bound values
            s.query(BlueskyPost).filter(BlueskyPost.uri.in_([r['uri'] for r in changed[i:i + 500]])) \
                .delete(synchronize_session=False)
        s.bulk_insert_mappings(BlueskyPost, changed)
        s.commit()


def _posts(get, uris: list[str]) -> list[dict]:
    return get('app.bsky.feed.getPosts', 'uris', uris).get('posts', [])


_cache = None


def prepared() -> dict:
    """The lookup cache, refreshed once per build: candidates from the week's daily narrative reports, the newest
    first (the same reports the Folklore page and the story pages show)"""
    global _cache
    if _cache is None:
        from app.narratives import latest_report
        from app.site.page_story import reports_by_day
        reports = [latest_report() or {}] + reports_by_day()
        uris = [u for r in reports for g in r.get('found', []) if (g.get('label') or {}).get('retold')
                for u in g.get('uris') or []]
        _cache = refresh(list(dict.fromkeys(uris))) if uris else load()
    return _cache


RULE = (f'{MIN_INTERACTIONS}+ likes, reposts, quotes and replies, or {MIN_BIG_ACCOUNT}+ from an account with '
        f'{MIN_FOLLOWERS:,}+ followers')
SCRIPT = '<script async src="https://embed.bsky.app/static/embed.js" charset="utf-8"></script>'
