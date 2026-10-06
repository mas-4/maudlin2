"""What people say, unprompted (#153, #142): a sample of public English Bluesky and Mastodon posts, for finding the
narratives people retell in their own words (folklore-shaped: rumors, legends, stock phrases), not only the stories
outlets cover.

Mastodon: the federated timeline of mas.to (one of the few big instances that serves it without an account), a few
pages a run, keeping only posts from people who opted in to being searchable (their account's "indexable" setting),
not marked as bots, without a content warning.

Each run listens to Bluesky's public stream (Jetstream, run by Bluesky for exactly this) for a few minutes. Kept: a
post's text, when it was written, whether it's a reply or a quote, and a salted fingerprint of its author (enough to
count distinct people, never to say who they are), and since Oct 6 the post's address (at://...), so that a narrative
can show a few of its posts that were already widely seen, embedded from Bluesky (app/bluesky_examples.py). Never
kept: images, video, links' previews, handles, names. Posts their authors labeled (adult content, gore and so on) are
skipped. A post deleted while we listen is deleted here too, and raw text and addresses are dropped after
RETENTION_DAYS; only the narratives found in it (app/narratives.py) are kept longer. No post is published as is: one is
only ever embedded from Bluesky itself, so a deleted post disappears."""
import hashlib
import re
import json
import os
import secrets
import sqlite3
import time
from datetime import datetime as dt, timedelta as td, timezone

from app.utils import Config, get_logger

logger = get_logger(__name__)

DB = os.path.join(Config.data, 'vernacular.sqlite')
SALT_FILE = os.path.join(Config.data, 'vernacular_salt')
JETSTREAM = 'wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post'
MINUTES = 5  # listened per run
RETENTION_DAYS = 30
MIN_CHARS = 20  # shorter is mostly "lol", emoji, single words
INSERT = ('INSERT OR IGNORE INTO post (key, author, created, collected, text, reply, quote, media, links, uri) '
          'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
INSERT_SOURCE = ('INSERT OR IGNORE INTO post (key, author, created, collected, text, reply, quote, media, links, '
                 'source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)')
MENTION = re.compile(r'@[\w.-]+(?:\.[a-z]{2,})+|@\w+')
LINK = re.compile(r'https?://(?:www\.)?([^/\s]+)\S*')
# Bluesky shows links in a post's text shortened and without https:// ("youtu.be/aZztV...", "twitch.tv/someone")
BARE_LINK = re.compile(r'(?<![\w@/.\[])(?:www\.)?((?:[a-z0-9-]+\.)+[a-z]{2,})/\S*', re.I)


def scrub(text: str) -> str:
    """Other people's handles become "@someone" and links just their site, before anything is stored."""
    text = LINK.sub(r'[link: \1]', MENTION.sub('@someone', text))
    return BARE_LINK.sub(lambda m: f'[link: {m.group(1).lower()}]', text).strip()


_news = None


def news_domains() -> set[str]:
    """The sites of the outlets we scrape: links to their articles are kept whole (public, and they tie a post to a
    story exactly); every other link is cut to its site."""
    global _news
    if _news is None:
        from urllib.parse import urlsplit
        from app.registry import Scrapers
        _news = {urlsplit(s.url).netloc.lower().removeprefix('www.') for s in Scrapers if getattr(s, 'url', None)}
    return _news


def article_links(urls) -> str | None:
    """The links among `urls` that go to an article on a site we scrape, without tracking parameters, as JSON."""
    from urllib.parse import urlsplit, urlunsplit
    out = []
    for url in urls:
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        host = parts.netloc.lower().removeprefix('www.')
        if host in news_domains() and len(parts.path) > 8:  # an article, not the homepage
            out.append(urlunsplit((parts.scheme or 'https', parts.netloc.lower(), parts.path, '', '')))
    return json.dumps(sorted(set(out))) if out else None


def bluesky_links(record: dict) -> list[str]:
    """Every link a Bluesky post carries: in its text's link markup and its link card (also inside a quote)."""
    urls = [f.get('uri', '') for facet in record.get('facets') or [] for f in facet.get('features') or []
            if 'link' in f.get('$type', '')]
    embed = record.get('embed') or {}
    for part in (embed, embed.get('media') or {}):
        external = part.get('external') or {}
        if external.get('uri'):
            urls.append(external['uri'])
    return urls


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=30)
    con.execute("""CREATE TABLE IF NOT EXISTS post (
        key TEXT PRIMARY KEY, author TEXT NOT NULL, created TEXT, collected TEXT NOT NULL, text TEXT NOT NULL,
        reply INTEGER NOT NULL DEFAULT 0, quote INTEGER NOT NULL DEFAULT 0, media INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'bluesky', links TEXT)""")
    if 'links' not in {row[1] for row in con.execute('PRAGMA table_info(post)')}:
        con.execute('ALTER TABLE post ADD COLUMN links TEXT')  # article links, added Oct 4
    if 'uri' not in {row[1] for row in con.execute('PRAGMA table_info(post)')}:
        con.execute('ALTER TABLE post ADD COLUMN uri TEXT')  # a Bluesky post's address, added Oct 6
    con.execute('CREATE INDEX IF NOT EXISTS ix_post_collected ON post (collected)')
    con.execute('CREATE INDEX IF NOT EXISTS ix_post_author ON post (author)')
    return con


def salt() -> str:
    """A secret made once, so the author fingerprints can't be matched back to accounts by anyone without it."""
    if not os.path.exists(SALT_FILE):
        with open(SALT_FILE, 'w') as f:
            f.write(secrets.token_hex(32))
        os.chmod(SALT_FILE, 0o600)
    with open(SALT_FILE) as f:
        return f.read().strip()


def fingerprint(value: str, pepper: str) -> str:
    return hashlib.sha256(f'{pepper}\n{value}'.encode()).hexdigest()[:24]


# Sexual spam its posters don't label: never stored
ADULT = re.compile(r'\b(only ?fans|fansly|nsfw|nudes?|porn\w*|horny|boobs|tits|milf|cock|pussy|xxx|sexting|'
                   r'cam ?girls?|goon\w*|hentai|onlyfan)\b', re.I)
ENGLISH_WORDS = {'the', 'and', 'to', 'of', 'a', 'in', 'is', 'it', 'that', 'for', 'you', 'this', 'on', 'with', 'are',
                 'be', 'have', 'not', 'was', 'but', 'they', 'what', 'just', 'so', 'my', 'all', 'if', 'about', 'we',
                 'like', 'he', 'she', 'do', 'at', 'from', 'can', 'will', 'or', 'me', 'his', 'her', 'their', 'an',
                 'i', 'your', 'how', 'who', 'no', 'one', 'there', 'when', 'out', 'up', 'people', 'by', 'has'}


def english(text: str) -> bool:
    """Mostly Latin letters and some common English words: posts often don't say their language, or say it wrong."""
    letters = [c for c in text if c.isalpha()]
    if not letters or sum(c.isascii() for c in letters) < 0.85 * len(letters):
        return False
    tokens = re.findall(r"[a-z']+", text.lower())
    return len(tokens) < 5 or sum(t in ENGLISH_WORDS for t in tokens) >= max(1, 0.12 * len(tokens))


def keep(record: dict) -> bool:
    """English text posts with something to say, that their authors didn't label as sensitive and aren't sex spam."""
    langs = record.get('langs') or []
    if langs and not any(str(lang).lower().startswith('en') for lang in langs):
        return False
    if (record.get('labels') or {}).get('values'):  # self-labels: porn, sexual, nudity, graphic-media, gore...
        return False
    text = (record.get('text') or '').strip()
    return len(text) >= MIN_CHARS and english(text) and not ADULT.search(text)


def clean() -> int:
    """Apply the current keep and scrub rules to what's already stored (after they change); returns how many posts
    were dropped or rewritten."""
    con = connect()
    rows = con.execute('SELECT key, text FROM post').fetchall()
    drop = [(k,) for k, t in rows if not english(t) or ADULT.search(t)]
    dropped = {k for k, in drop}
    rewrite = [(scrub(t), k) for k, t in rows if k not in dropped and scrub(t) != t]
    con.executemany('DELETE FROM post WHERE key = ?', drop)
    con.executemany('UPDATE post SET text = ? WHERE key = ?', rewrite)
    con.commit()
    con.close()
    return len(drop) + len(rewrite)


def row(message: dict, pepper: str):
    """('create', values) for a post to keep, ('delete', key) for a deleted post, or None."""
    commit = message.get('commit') or {}
    if message.get('kind') != 'commit' or commit.get('collection') != 'app.bsky.feed.post':
        return None
    did, rkey = message.get('did', ''), commit.get('rkey', '')
    key = fingerprint(f'{did}/{rkey}', pepper)
    if commit.get('operation') == 'delete':
        return 'delete', key
    record = commit.get('record') or {}
    if commit.get('operation') != 'create' or not keep(record):
        return None
    embed = record.get('embed') or {}
    kind = embed.get('$type', '')
    now = dt.now(timezone.utc).isoformat(timespec='seconds')
    return 'create', (key, fingerprint(did, pepper), record.get('createdAt'), now, scrub(record['text']),
                      int('reply' in record), int('record' in kind),
                      int('images' in kind or 'video' in kind or 'media' in kind), article_links(bluesky_links(record)),
                      f'at://{did}/app.bsky.feed.post/{rkey}' if did and rkey else None)


def sample(minutes: float = MINUTES, url: str = JETSTREAM) -> int:
    """Listen for `minutes` and store what to keep; returns how many posts were stored."""
    import websocket
    pepper = salt()
    con = connect()
    stored = deleted = 0
    deadline = time.time() + minutes * 60
    ws = None
    try:
        ws = websocket.create_connection(url, timeout=30)
        batch = []
        while time.time() < deadline:
            parsed = row(json.loads(ws.recv()), pepper)
            if parsed is None:
                continue
            what, value = parsed
            if what == 'delete':
                deleted += con.execute('DELETE FROM post WHERE key = ?', (value,)).rowcount
            else:
                batch.append(value)
            if len(batch) >= 500:
                stored += con.executemany(INSERT, batch).rowcount
                con.commit()
                batch = []
        stored += con.executemany(INSERT, batch).rowcount
    except Exception as e:  # the stream down or slow: keep what came in, try again next run
        logger.warning("Bluesky sample stopped early: %s", e)
    finally:
        if ws is not None:
            ws.close()
        cutoff = (dt.now(timezone.utc) - td(days=RETENTION_DAYS)).isoformat(timespec='seconds')
        dropped = con.execute('DELETE FROM post WHERE collected < ?', (cutoff,)).rowcount
        con.commit()
        con.close()
    logger.info("Bluesky sample: %d posts kept, %d deleted by their authors, %d past %d days dropped",
                stored, deleted, dropped, RETENTION_DAYS)
    return stored


MASTODON = 'https://mas.to/api/v1/timelines/public'
MASTODON_PAGES = 3  # requests a run, 40 posts each


def mastodon_row(status: dict, pepper: str):
    """The values to store for a Mastodon status, or None for one to leave alone."""
    from bs4 import BeautifulSoup
    account = status.get('account') or {}
    if status.get('reblog') or not account.get('indexable') or account.get('bot') or status.get('sensitive') \
            or status.get('spoiler_text') or (status.get('language') or 'en') != 'en':
        return None
    soup = BeautifulSoup(status.get('content') or '', 'html.parser')
    text = scrub(soup.get_text(' ', strip=True))
    links = [a.get('href', '') for a in soup.find_all('a')] + [(status.get('card') or {}).get('url') or '']
    if len(text) < MIN_CHARS or not english(text) or ADULT.search(text):
        return None
    now = dt.now(timezone.utc).isoformat(timespec='seconds')
    return (fingerprint(status.get('uri', ''), pepper), fingerprint(account.get('uri', ''), pepper),
            status.get('created_at'), now, text, int(bool(status.get('in_reply_to_id'))), int(bool(status.get('quote'))),
            int(bool(status.get('media_attachments'))), article_links(links), 'mastodon')


def mastodon_sample(pages: int = MASTODON_PAGES) -> int:
    """A few pages of the federated timeline, spaced a few seconds apart; returns how many posts were stored."""
    import requests as rq
    pepper = salt()
    con = connect()
    stored, max_id = 0, None
    try:
        for page in range(pages):
            params = {'limit': 40, **({'max_id': max_id} if max_id else {})}
            r = rq.get(MASTODON, params=params, headers={'User-Agent': 'Maudlin Bot (https://bignews.day)'},
                       timeout=30)
            r.raise_for_status()
            statuses = r.json()
            if not statuses:
                break
            max_id = statuses[-1]['id']
            rows = [v for v in (mastodon_row(x, pepper) for x in statuses) if v]
            stored += con.executemany(INSERT_SOURCE, rows).rowcount
            con.commit()
            if page < pages - 1:
                time.sleep(5)
    except Exception as e:
        logger.warning("Mastodon sample stopped early: %s", e)
    finally:
        con.close()
    logger.info("Mastodon sample: %d posts kept", stored)
    return stored
