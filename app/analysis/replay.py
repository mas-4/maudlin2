"""The Replay: passages heard word for word on many shows (a clip of a speech, a campaign ad, a statement, a sponsor
read), found by text reuse across our show transcripts (app/transcribe.py).

Each transcript is cut into overlapping 12-word runs ("shingles", hashed with numpy). A shingle heard on three or more
different shows is shared; a transcript's shared shingles a word or two apart join into one passage, and passages
that share a shingle are one replayed passage, heard wherever any of them was. Pieces of one clip that a show's
transcript breaks apart (a word heard differently) are put back together when they sit side by side in most of the
same episodes. Twelve words in the same order are rarely said twice by chance; the cost is that a clip trimmed or
transcribed differently on one show can miss it there.

Each passage is then sorted, by rules that can be read off its words (classify gives the words that decided it):
- glitch: a transcription loop (Whisper repeating itself, "you know you know you know..."): few different words;
- campaign: a political ad that says so ("paid for by", "approve this message");
- ad: a sponsor read or a promo for another show ("promo code", "terms apply", "at example com", "wherever you get
  your podcasts"), or one where shopping words ("free", "save", "order", "shipping"...) are a large share of it;
- clip: everything else, mostly news audio played on several shows.

The window is the 14 days up to the newest transcript: the page shows what was heard in the last week, and the week
behind it catches the start of anything still on the air (the Acton ad ran Oct 20-26). 21 days found little more,
and the transcripts made before Oct 20 carry more transcription loops. The result is cached in the data folder by the
transcripts it read, so an hourly build recomputes only when new transcripts have come in (a few seconds on two
weeks, Oct 28)."""
import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime as dt, timedelta as td

import numpy as np

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

K = 12  # words in a shingle
DAYS = 14  # the window read, up to the newest transcript
MIN_SHOWS = 3  # a passage counts as replayed when heard on this many different shows
GAP = 2  # shared shingles at most this many words apart are one passage
BESIDE = 15  # a clip this close to a sponsor read in most of its episodes is part of the read
NEAR = 30  # pieces at most this many words apart in an episode may be one clip...
TOGETHER = 0.75  # ...when they sit that close in this share of the episodes of the one heard less
GLITCH_RATIO = 0.35  # a passage with fewer different words than this share of its words is a transcription loop
KEEP_WORDS = 160  # words of each passage kept in the cache (the page shows about 40)
VERSION = 7  # bump to recompute the cache when the method changes
MUL = np.uint64(1099511628211)

# A web address read out: "at wayfair com", "visit simplisafe com slash", "claude ai slash spotify"
ADDRESS = r"(?:at|to|visit|on|see) [a-z0-9]+ (?:dot )?(?:com|org|net|edu|io|ai|co)\b|[a-z0-9]+ (?:dot )?(?:com|org|net|edu|io|ai) slash\b"
# Sponsor reads and promos: phrases that hardly occur outside them
AD = re.compile(
    r"\b(?:promo code|offer code|use code|with code|code \w+ at checkout|percent off|up to \d+ (?:percent )?off"
    r"|\d+ off (?:your|select|everything|carrier|your first)|free shipping|(?:terms|restrictions)(?: and \w+)*(?: requirements)? apply"
    r"|taxes and fees|fees may apply|not available in all|available in select states|for details|nmls|member fdic"
    r"|sponsored by|brought to you by|(?:supported|presented) by|support for (?:npr|this|the)|this message comes? from"
    r"|messages? from our sponsors|wherever you get (?:your )?podcasts|new episodes every|listen now|podcast from"
    r"|this week on \w+|on the \w+ app|app store|google play|download the \w+ app|first (?:month|box) free"
    r"|money back guarantee|limited time offer|order (?:now|online|today)|call now|sign up (?:today|now|at)"
    r"|where you heard about|save (?:up to|over|through|with|time and money)|(?:fall|holiday|big) savings"
    r"|shop (?:now|at|today|certified)|try \w+ (?:for )?free|schedule your appointment|" + ADDRESS + r")\b")
CAMPAIGN = re.compile(r"\b(?:paid for by|approved? (?:of )?this message|i approve|not authorized by any candidate"
                      r"|authorized by \w+ for|political action committee|super pac|vote early|bank your vote"
                      r"|find your polling place)\b")
# Shopping words: an ad when they make up a large share of a passage with no phrase above
SHOPPING = {'free', 'save', 'saving', 'savings', 'order', 'orders', 'shipping', 'shop', 'sale', 'deal', 'deals',
            'offer', 'offers', 'price', 'priced', 'prices', 'customers', 'checkout', 'brand', 'brands', 'quality',
            'premium', 'discount', 'returns', 'delivery', 'deliveries', 'purchase', 'subscription', 'trial',
            'guarantee', 'insurance', 'products', 'product', 'formula', 'supplement', 'business', 'businesses',
            'platform', 'app', 'apps', 'plan', 'plans', 'switch', 'overpaying', 'recommended', 'gift', 'accessories',
            'reviews', 'bottles', 'software', 'fees', 'tickets'}
SHOPPING_SHARE = 0.06
SHOPPING_KINDS = 3  # different shopping words needed besides the share


def words(text: str) -> list[str]:
    """Lowercase words, punctuation dropped (apostrophes kept: "don't")"""
    return re.sub(r"[^a-z0-9' ]+", ' ', (text or '').lower().replace('’', "'")).split()


def shingles(ids: np.ndarray, k: int = K) -> np.ndarray:
    """A 64-bit hash for every run of k word ids (len(ids) - k + 1 of them; none for a shorter text)"""
    m = len(ids) - k + 1
    if m <= 0:
        return np.zeros(0, dtype=np.uint64)
    h = np.zeros(m, dtype=np.uint64)
    with np.errstate(over='ignore'):
        for j in range(k):
            h = h * MUL + ids[j:j + m]
    return h


def classify(text: str) -> tuple[str, str]:
    """What a passage is, with the words that decided it: ('glitch' | 'campaign' | 'ad' | 'clip', reason)"""
    w = words(text)
    if len(w) >= K and len(set(w)) / len(w) < GLITCH_RATIO:
        return 'glitch', f'{len(set(w))} different words in {len(w)}'
    plain = ' '.join(w)
    if m := CAMPAIGN.search(plain):
        return 'campaign', f'"{m.group(0)}"'
    if m := AD.search(plain):
        return 'ad', f'"{m.group(0)}"'
    shop = [x for x in w if x in SHOPPING]
    if len(set(shop)) >= SHOPPING_KINDS and len(shop) / len(w) >= SHOPPING_SHARE:
        return 'ad', 'shopping words: ' + ', '.join(f'"{x}"' for x in sorted(set(shop))[:4])
    return 'clip', ''


def episode_time(segments: list[dict], index: int) -> float | None:
    """Seconds into the episode where its `index`-th word (as words() counts the joined text) was said, from the
    start of the timed segment holding it; None past the end"""
    n = 0
    for seg in segments or []:
        c = len(words(seg.get('text', '')))
        if index < n + c:
            return float(seg.get('start') or 0)
        n += c
    return None


class _Union:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def root(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def join(self, a: int, b: int):
        a, b = self.root(a), self.root(b)
        if a != b:
            self.parent[a] = b


def _parts(transcripts: list[dict], k: int, min_shows: int) -> list[tuple[int, int, int, list]]:
    """Runs of shared shingles within each transcript: (transcript index, first word, end word, their hashes)"""
    vocab = {}
    srcs = sorted({t['source'] for t in transcripts})
    sidx = {s: i for i, s in enumerate(srcs)}
    H, S, I, P = [], [], [], []
    for n, t in enumerate(transcripts):
        ids = np.fromiter((vocab.setdefault(w, len(vocab) + 1) for w in t['words']), dtype=np.uint64,
                          count=len(t['words']))
        h = shingles(ids, k)
        if not len(h):
            continue
        H.append(h)
        S.append(np.full(len(h), sidx[t['source']], dtype=np.int32))
        I.append(np.full(len(h), n, dtype=np.int32))
        P.append(np.arange(len(h), dtype=np.int32))
    if not H:
        return []
    H, S, I, P = (np.concatenate(x) for x in (H, S, I, P))
    order = np.lexsort((S, H))  # shows per shingle: each (shingle, show) pair once
    hs, ss = H[order], S[order]
    new = np.ones(len(hs), bool)
    new[1:] = (hs[1:] != hs[:-1]) | (ss[1:] != ss[:-1])
    uh, counts = np.unique(hs[new], return_counts=True)
    shared = uh[counts >= min_shows]
    if not len(shared):
        return []
    mask = np.isin(H, shared)
    byitem = defaultdict(list)
    for h, i, p in zip(H[mask].tolist(), I[mask].tolist(), P[mask].tolist()):
        byitem[i].append((p, h))
    parts = []
    for i, hits in byitem.items():
        hits.sort()
        start = prev = hits[0][0]
        hashes = []
        for p, h in hits + [(None, None)]:
            if p is not None and p <= prev + GAP:
                prev = p
                hashes.append(h)
                continue
            parts.append((i, start, prev + k, hashes))
            if p is not None:
                start = prev = p
                hashes = [h]
    return parts


def find(transcripts: list[dict], k: int = K, min_shows: int = MIN_SHOWS) -> list[dict]:
    """The passages heard on at least `min_shows` different shows. Each transcript: {'source', 'words'} (and anything
    else). Returns one dict per replayed passage: 'episodes' {transcript index: [(first word, end word), ...]} and
    'sources', sorted."""
    parts = _parts(transcripts, k, min_shows)
    # Passages sharing a shingle are one replayed passage
    u = _Union(len(parts))
    first = {}
    for n, (_, _, _, hashes) in enumerate(parts):
        for h in hashes:
            u.join(first.setdefault(h, n), n)
    groups = defaultdict(list)
    for n in range(len(parts)):
        groups[u.root(n)].append(n)
    groups = [g for g in groups.values()
              if len({transcripts[parts[n][0]]['source'] for n in g}) >= min_shows]
    # Pieces of one clip: side by side in most of the same episodes
    episodes = [{parts[n][0] for n in g} for g in groups]
    by_item = defaultdict(list)
    for gi, g in enumerate(groups):
        for n in g:
            by_item[parts[n][0]].append((parts[n][1], parts[n][2], gi))
    near = Counter()
    for spans in by_item.values():
        spans.sort()
        pairs = set()
        for (_, b1, g1), (a2, _, g2) in zip(spans, spans[1:]):
            if g1 != g2 and a2 - b1 <= NEAR:
                pairs.add((min(g1, g2), max(g1, g2)))
        near.update(pairs)
    u = _Union(len(groups))
    for (g1, g2), c in near.items():
        if c >= 2 and c >= TOGETHER * min(len(episodes[g1]), len(episodes[g2])):
            u.join(g1, g2)
    merged = defaultdict(list)
    for gi in range(len(groups)):
        merged[u.root(gi)].append(gi)
    out = []
    for gis in merged.values():
        eps = defaultdict(list)
        for gi in gis:
            for n in groups[gi]:
                eps[parts[n][0]].append((parts[n][1], parts[n][2]))
        out.append({'episodes': {i: sorted(s) for i, s in eps.items()},
                    'sources': sorted({transcripts[i]['source'] for i in eps})})
    return out


def stretches_of(spans: list[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    """Sorted spans of one episode in runs at most NEAR words apart (a sponsor read heard twice in one episode is two)"""
    out = []
    for a, b in spans:
        if out and a - out[-1][-1][1] <= NEAR:
            out[-1].append((a, b))
        else:
            out.append([(a, b)])
    return out


def as_said(t: dict, a: int, b: int) -> str:
    """Words a to b of a transcript as its text has them, with their capitals and punctuation ("Amy Acton's mother,"),
    or lowercase as matched when the text's words don't line up with the matched ones"""
    text = (t['text'] or '').replace('’', "'")
    tokens = list(re.finditer(r"[A-Za-z0-9']+", text))
    if len(tokens) != len(t['words']) or not a < b <= len(tokens):
        return ' '.join(t['words'][a:b])
    return ' '.join(text[tokens[a].start():tokens[b - 1].end()].split())


def _iso(t: dt) -> str:
    return t.replace(microsecond=0).isoformat()


def build(transcripts: list[dict], segments_of=lambda ids: {}) -> list[dict]:
    """The replayed passages of these transcripts (each: id, source, title, url, published (naive UTC), text), most
    shows first, each with its kind, its words (from the episode where most of it was heard) and its airings (one per
    episode, with the time in it from segments_of(transcript ids) -> {id: segments}, where they line up)"""
    from app.sidefeeds import BY_KEY
    seen, kept = set(), []
    for t in transcripts:  # a feed that lists one episode twice: count it once
        sig = (t['source'], hashlib.sha1(t['text'].encode()).digest())
        if sig not in seen:
            seen.add(sig)
            kept.append(dict(t, words=words(t['text'])))
    found = find(kept)
    segs = segments_of(sorted({kept[i]['id'] for f in found for i in f['episodes']}))
    lined_up = {i: len(words(' '.join(s.get('text', '') for s in seg))) == len(t['words'])
                for t in kept if (i := t['id']) in segs for seg in [segs[i]]}
    out = []
    for f in found:
        # Its words: the longest stretch of it in one episode (pieces of it at most NEAR words apart)
        stretches = [(sum(b - a for a, b in s), -i, i, s[0][0], s[-1][1])
                     for i, spans in f['episodes'].items() for s in stretches_of(spans)]
        _, _, best, a, b = max(stretches)
        said = kept[best]['words'][a:b]
        kind, why = classify(' '.join(said))
        airings = []
        for i, spans in f['episodes'].items():
            t = kept[i]
            src = BY_KEY.get(t['source'], {})
            at = episode_time(segs.get(t['id']), spans[0][0]) if lined_up.get(t['id']) else None
            airings.append({'id': t['id'], 'source': t['source'], 'show': src.get('name', t['source']),
                            'group': src.get('group', 'center'), 'title': t['title'], 'url': t['url'],
                            'published': _iso(t['published']), 'at': at})
        airings.sort(key=lambda x: (x['published'], x['source']))
        out.append({'id': hashlib.sha1(' '.join(said[:K]).encode()).hexdigest()[:10],
                    'kind': kind, 'why': why, 'text': as_said(kept[best], a, min(b, a + KEEP_WORDS)),
                    'words': len(said),
                    'shows': len(f['sources']), 'sources': f['sources'], 'airings': airings,
                    'first': airings[0]['published'], 'last': airings[-1]['published']})
    beside_reads(out, [f['episodes'] for f in found], kept)
    out.sort(key=lambda p: (-p['shows'], -len(p['airings']), p['first'], p['id']))
    return out


def beside_reads(passages: list[dict], episodes: list[dict], transcripts: list[dict]):
    """A clip that sits right against a sponsor read (BESIDE words or less) in at least half its episodes, on two
    shows or more, is a piece of that read the transcripts broke off ("z biotics has sold more than 14 million
    bottles..."): it becomes an ad too, saying which read it sits beside. episodes[n] holds passages[n]'s spans."""
    reads = defaultdict(list)  # transcript index -> [(first word, end word, the read's index)]
    for n, (p, eps) in enumerate(zip(passages, episodes)):
        if p['kind'] == 'ad':
            for i, spans in eps.items():
                reads[i] += [(a, b, n) for a, b in spans]
    for p, eps in zip(passages, episodes):
        if p['kind'] != 'clip':
            continue
        near = Counter()
        shows = defaultdict(set)
        for i, spans in eps.items():
            for n in {n for a, b in spans for ra, rb, n in reads.get(i, ()) if ra - b <= BESIDE and a - rb <= BESIDE}:
                near[n] += 1
                shows[n].add(transcripts[i]['source'])
        best = max(near, key=near.get, default=None)
        if best is not None and near[best] * 2 >= len(eps) and len(shows[best]) >= 2:
            p['kind'], p['why'] = 'ad', f'beside the read "{" ".join(passages[best]["text"].split()[:6])}…"'


def _key(rows: list) -> str:
    h = hashlib.sha1(f'v{VERSION} k{K} d{DAYS} s{MIN_SHOWS}'.encode())
    for r in sorted(rows):
        h.update(f'{r[0]}:{r[1]};'.encode())
    return h.hexdigest()


def cache_path() -> str:
    return os.path.join(Config.data, 'replay.json')


def _window() -> tuple[list, dt | None]:
    """(transcript id, when made) of every usable transcript in the window, and the newest one's publish time"""
    from sqlalchemy import func
    from app.models import Session, SideItem, SideTranscript
    usable = ~SideTranscript.model.like('failed%') & ~SideTranscript.model.like('skipped%')
    with Session() as s:
        newest = s.query(func.max(SideItem.published)).join(SideTranscript, SideTranscript.item_id == SideItem.id) \
            .filter(usable).scalar()
        if newest is None:
            return [], None
        rows = s.query(SideTranscript.id, SideTranscript.created).join(SideItem, SideTranscript.item_id == SideItem.id) \
            .filter(usable, SideItem.published >= newest - td(days=DAYS)).all()
    return [(r[0], str(r[1])) for r in rows], newest


def _transcripts(ids: list[int]) -> list[dict]:
    from app.models import Session, SideItem, SideTranscript
    out = []
    with Session() as s:
        for n in range(0, len(ids), 500):
            q = s.query(SideTranscript.id, SideItem.source, SideItem.title, SideItem.url, SideItem.published,
                        SideTranscript.text).join(SideItem, SideTranscript.item_id == SideItem.id) \
                .filter(SideTranscript.id.in_(ids[n:n + 500]))
            out += [{'id': r[0], 'source': r[1], 'title': r[2], 'url': r[3], 'published': r[4], 'text': r[5]}
                    for r in q]
    return sorted(out, key=lambda t: t['id'])


def _segments(ids: list[int]) -> dict:
    from app.models import Session, SideTranscript
    out = {}
    with Session() as s:
        for n in range(0, len(ids), 500):
            for i, seg in s.query(SideTranscript.id, SideTranscript.segments) \
                    .filter(SideTranscript.id.in_(ids[n:n + 500])):
                try:
                    out[i] = json.loads(seg or '[]')
                except ValueError:
                    out[i] = []
    return out


def load() -> dict:
    """The replayed passages of the last DAYS of transcripts: {'key', 'transcripts', 'since', 'until', 'seconds',
    'passages'}; recomputed only when the transcripts in the window change"""
    rows, newest = _window()
    key = _key(rows)
    cached = read_json(cache_path(), {})
    if cached.get('key') == key:
        return cached
    started = time.time()
    transcripts = _transcripts([r[0] for r in rows])
    passages = build(transcripts, _segments)
    result = {'key': key, 'transcripts': len(transcripts), 'days': DAYS,
              'since': _iso(newest - td(days=DAYS)) if newest else None, 'until': _iso(newest) if newest else None,
              'seconds': round(time.time() - started, 1), 'passages': passages}
    write_json(cache_path(), result)
    logger.info("Replay: %d replayed passages in %d transcripts (%.0f s)", len(passages), len(transcripts),
                result['seconds'])
    return result
