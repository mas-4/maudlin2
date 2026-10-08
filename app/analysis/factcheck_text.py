"""The text of each fact-check, not just its feed's headline and blurb (Oct 8: the person often opened the piece to see
what was actually claimed, so their filing rested on more than the claim the models were shown). Taken from the feed
where it carries the whole piece (FactCheck.org, Lead Stories, NewsGuard: content:encoded or Atom content), else read
from the page itself, politely: one site at a time with PAGE_GAP seconds between requests to the same site, at most
PAGES_PER_RUN pages a run, robots.txt obeyed. Kept for good in TEXTS (url -> the piece's text), cut to KEEP
characters."""
import os
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

TEXTS = os.path.join(Config.data, 'factcheck_texts.json')
USER_AGENT = 'Maudlin Bot (https://bignews.day)'
KEEP = 8000
PAGE_GAP = 20  # seconds between two requests to one site
PAGES_PER_RUN = 24
MIN_TEXT = 300  # less than this read from a page is a menu or a paywall, not the piece
MAX_TRIES = 3  # pages that keep failing are left alone (their label falls back to the feed's blurb)


def _clean(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html or '', 'html.parser')
    for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside', 'form', 'figure', 'noscript']):
        tag.decompose()
    root = soup.find('article') or soup.find('main') or soup.body or soup
    paragraphs = [' '.join(p.get_text(' ').split()) for p in root.find_all(['p', 'li', 'blockquote', 'h2', 'h3'])]
    text = '\n'.join(p for p in paragraphs if len(p) > 1)
    return text or ' '.join(root.get_text(' ').split())


def from_feeds(sources: list[dict]) -> dict[str, str]:
    """url -> text, from the fact-check feeds that carry whole pieces (one request a feed)"""
    from bs4 import BeautifulSoup
    out = {}
    for s in sources:
        try:
            r = requests.get(s['url'], timeout=Config.timeout, headers={'User-Agent': USER_AGENT})
            r.raise_for_status()
        except requests.RequestException as e:
            logger.info("Fact-check texts: feed %s unread (%s)", s['name'], type(e).__name__)
            continue
        soup = BeautifulSoup(r.content, 'xml')
        for item in soup.find_all('item') or soup.find_all('entry'):
            link = item.find('link')
            url = (link.get('href') or link.get_text() if link else '').strip()
            body = item.find('encoded') or item.find('content')
            if url and body:
                text = _clean(body.get_text())
                if len(text) >= MIN_TEXT:
                    out[url] = text[:KEEP]
    return out


class Polite:
    """Pages read one site at a time, PAGE_GAP seconds apart per site, only where robots.txt allows"""

    def __init__(self):
        self.last, self.robots = {}, {}

    def allowed(self, url: str) -> bool:
        host = urlparse(url).netloc
        if host not in self.robots:
            # Read with our own name: Python's reader calls itself Python-urllib, which Cloudflare refuses, and it
            # takes a refusal as 'nothing allowed' (Oct 8: every Snopes page skipped)
            rp = RobotFileParser()
            try:
                r = requests.get(f'https://{host}/robots.txt', timeout=Config.timeout, headers={'User-Agent': USER_AGENT})
                if r.status_code in (401, 403):
                    rp = None
                elif r.ok:
                    rp.parse(r.text.splitlines())
                else:
                    rp.parse([])  # no robots.txt: nothing asked of us
            except requests.RequestException:
                rp = None  # unreadable now: no pages from the site this run
            self.robots[host] = rp
        rp = self.robots[host]
        return bool(rp) and rp.can_fetch(USER_AGENT, url)

    def get(self, url: str) -> str | None:
        host = urlparse(url).netloc
        wait = self.last.get(host, 0) + PAGE_GAP - time.time()
        if wait > 0:
            time.sleep(wait)
        self.last[host] = time.time()
        try:
            r = requests.get(url, timeout=Config.timeout, headers={'User-Agent': USER_AGENT})
            r.raise_for_status()
            return r.text
        except requests.RequestException as e:
            logger.info("Fact-check texts: %s unread (%s)", url, type(e).__name__)
            return None


def gather(items: list[dict], sources: list[dict], budget: float | None = None) -> dict:
    """The text of each fact-check in `items` not kept yet: from the feeds, then pages (PAGES_PER_RUN at most, sites
    taken in turn so no one site is asked twice in a row); every text kept, url -> {'text', 'from'} or {'tries'}"""
    store = read_json(TEXTS, {})
    todo = [i for i in items if not store.get(i['url'], {}).get('text') and store.get(i['url'], {}).get('tries', 0) < MAX_TRIES]
    if not todo:
        return store
    started = time.time()
    feeds = from_feeds([s for s in sources if s['kind'] == 'fact-check'])
    for i in todo:
        if feeds.get(i['url']):
            store[i['url']] = {'text': feeds[i['url']], 'from': 'feed'}
    by_host = {}
    for i in todo:
        if not store.get(i['url'], {}).get('text'):
            by_host.setdefault(urlparse(i['url']).netloc, []).append(i['url'])
    order = []  # round robin over the sites
    while any(by_host.values()) and len(order) < PAGES_PER_RUN:
        for h in list(by_host):
            if by_host[h]:
                order.append(by_host[h].pop(0))
    polite = Polite()
    for url in order:
        if budget is not None and time.time() - started > budget:
            break
        if not polite.allowed(url):
            store[url] = {'tries': store.get(url, {}).get('tries', 0) + 1}  # robots.txt says no, or couldn't be read
            continue
        html = polite.get(url)
        text = _clean(html) if html else ''
        store[url] = ({'text': text[:KEEP], 'from': 'page'} if len(text) >= MIN_TEXT
                      else {'tries': store.get(url, {}).get('tries', 0) + 1})
    write_json(TEXTS, store)
    got = sum(1 for i in todo if store.get(i['url'], {}).get('text'))
    logger.info("Fact-check texts: %d of %d new read (%d from feeds)", got, len(todo), sum(1 for i in todo if i['url'] in feeds))
    return store


def text_of(url: str, store: dict | None = None) -> str:
    return ((store if store is not None else read_json(TEXTS, {})).get(url) or {}).get('text', '')
