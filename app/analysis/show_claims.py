"""What's told on the shows we follow (Oct 7): every transcribed podcast, call-in show and video show (app/sidefeeds.py,
app/transcribe.py), read for the claims told or argued over on it, so the folklore page hears talk radio and
podcasts, right, left and center, beside what people post and what fact-checkers examine. Its claims are filed in our
motif index like theirs (source: the show's name), so a motif told by a caller and posted online is one entry.

Built like the Focus Group reader (app/analysis/focus_group.py), whose checks it shares: the bigger local model reads
each episode in chunks; a claim is kept only if its quote is in that part of the transcript, not a quote already used,
and the quote supports it. Each claim says who told it (host, guest, caller, a played clip), as the transcript has no
speaker names. Quotes stay in the local checker; the site shows claims in our words, never the quotes or callers.
The hourly newscasts (read for their running order) and the Focus Group (read by its own reader) aren't read here."""
import json
import os
import time
from datetime import datetime as dt
from datetime import timedelta as td

from app.analysis import focus_group, llm
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

STORE = os.path.join(Config.data, 'show_claims.json')  # episode url -> its claims, filled chunk by chunk
RETOLD = os.path.join(Config.data, 'show_claims_retold.json')  # retold(), kept each run for the folklore page
MODEL = 'gemma4:26b'
CHUNK = 6000  # characters of transcript a call
DAYS = 7  # episodes published this recently
SKIP = {'focusgroup', 'nprnewsnow', 'abcupdate', 'bloombergnow'}  # read elsewhere (focus_group.py, running_order.py), or
# an hourly news bulletin: what it reports is the news, not what people tell
KINDS = {'call-in': 'a call-in radio show', 'podcast': 'a podcast', 'video': 'a video show'}
SPEAKERS = ['host', 'guest', 'caller', 'clip']
PROMPT = """This is part of an episode of {show}, {kind} ("{title}"). The transcript has no speaker names and may \
include ads.

{text}

List the claims about politics and public life told or argued over in this part: what someone says is true, why \
they say things happen, what they say someone is like, stories they pass on. Claims the speaker asserts, not ones \
they quote only to knock down. Not wishes or plans ("we need lower taxes", "I'm voting for her"), not ads, not the \
show's own business. For each:
claim: one plain sentence, the way it's told: what the speaker says is true. Name who it's about as the speaker \
means it ("Democrats", "Trump", "the Fed"), never "the speaker" or "his opponents"
quote: the speaker's own words, at most 25 words, copied from the transcript
speaker: "host" (the show's own hosts), "guest" (someone the hosts interview), "caller" (a listener calling in), \
"clip" (a recording the show plays: a politician's speech, another show; hosts often play a clip and then react to \
it, and what the clip says is the clip's, not the hosts'), or "" if unclear
Up to five, the ones most central to this part; none if there are none."""
SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string", "maxLength": 400},
    "claims": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
        "claim": {"type": "string", "maxLength": 240}, "quote": {"type": "string", "maxLength": 240},
        "speaker": {"type": "string", "enum": SPEAKERS + ['']}}, "required": ["claim", "quote", "speaker"]}}},
    "required": ["reason", "claims"]}
WHO = {'host': ('A show host', 'host'), 'guest': ('A guest on a show', 'guest'), 'caller': ('A caller to a radio show', 'caller'),
       'clip': ('Someone in a clip a show played', 'speaker'), '': ('Someone on a show', 'speaker')}


def load() -> dict:
    return read_json(STORE, {})


def save(store: dict):
    write_json(STORE, store, ensure_ascii=False)


def episodes(days: int = DAYS) -> list[dict]:
    """Every transcribed show episode of the last `days`, newest first, cut into CHUNK-sized parts"""
    from app import sidefeeds
    from app.models import Session, SideItem, SideTranscript
    since = dt.now() - td(days=days)
    with Session() as s:
        rows = s.query(SideItem.source, SideItem.title, SideItem.url, SideItem.published, SideTranscript.segments).join(
            SideTranscript, SideTranscript.item_id == SideItem.id).filter(
            SideItem.published >= since, SideItem.source.notin_(SKIP)).order_by(SideItem.published.desc()).all()
    out = []
    for source, title, url, published, segments in rows:
        src = sidefeeds.source_for(source) or {}
        if src.get('kind') not in KINDS and source != 'surrounded':
            continue
        chunks, text, at = [], '', 0.0
        for seg in json.loads(segments or '[]'):
            if not text:
                at = seg.get('start', 0.0)
            text += seg['text'].strip() + ' '
            if len(text) >= CHUNK:
                chunks.append({'at': at, 'text': text.strip()})
                text = ''
        if text.strip():
            chunks.append({'at': at, 'text': text.strip()})
        out.append({'source': source, 'show': src.get('name', source), 'kind': KINDS.get(src.get('kind'), 'a show'),
                    'lean': src.get('group'), 'title': title, 'url': url, 'date': str(published)[:10], 'chunks': chunks})
    return out


def read_part(ep: dict, chunk: dict) -> tuple[list[dict], list[dict]]:
    """(kept, dropped) claims of one part of an episode"""
    answer = llm.complete_json(PROMPT.format(show=ep['show'], kind=ep['kind'], title=ep['title'], text=chunk['text']),
                               SCHEMA, max_tokens=1000, model=MODEL)
    found = []
    for c in (answer or {}).get('claims', []):
        claim = ' '.join(c.get('claim', '').split())
        if sum(ch.isalpha() for ch in claim) < 12:  # '...' and other empty fills
            continue
        speaker = c.get('speaker') if c.get('speaker') in SPEAKERS else ''
        found.append({'claim': claim, 'quote': c.get('quote', '').strip(), 'speaker': speaker, 'at': round(chunk['at'])})
    kept, dropped = focus_group.checked(found, chunk['text'])
    for c in list(kept):
        who, noun = WHO[c['speaker']]
        if focus_group.supported(c['claim'], c['quote'], who=who, noun=noun) is False:
            kept.remove(c)
            dropped.append(dict(c, why="the quote doesn't support the claim"))
    return kept, dropped


def extract(budget: float | None = None) -> dict:
    """Read the episodes not read yet, newest first, chunk by chunk, saving as it goes, for at most `budget` seconds
    (the next run carries on); then keep what's retold for the folklore page"""
    store = load()
    if llm.backend() is None:
        return store
    calls = read_episodes(store, budget)
    if calls or not os.path.exists(RETOLD):
        write_json(RETOLD, retold(store))
    return store


def read_episodes(store: dict, budget: float | None) -> int:
    started, calls = time.time(), 0
    for ep in episodes():
        entry = store.setdefault(ep['url'], {k: ep[k] for k in ('source', 'show', 'lean', 'title', 'date')} | {'read': 0, 'claims': []})
        while entry['read'] < len(ep['chunks']):
            if budget is not None and time.time() - started > budget:
                logger.info("Show claims: %d parts read this run; more next run", calls)
                return calls
            kept, dropped = read_part(ep, ep['chunks'][entry['read']])
            entry['claims'] += kept
            entry.setdefault('dropped', []).extend(dropped)
            entry['read'] += 1
            entry['chunks'] = len(ep['chunks'])
            calls += 1
            save(store)
    if calls:
        logger.info("Show claims: %d parts read; %d claims from %d episodes", calls,
                    sum(len(e['claims']) for e in store.values()), len(store))
    return calls


def kept_retold() -> list[dict]:
    """What the last run found retold (retold()), without embedding anything: for the site build"""
    return read_json(RETOLD, [])


MIN_SHOWS = 2  # a claim is retold once this many shows tell it (or this many callers, to any shows)
SOURCE = 'shows'  # the motif index's source for a retold claim (as 'narrative' is for what people post)


def retold(store: dict | None = None) -> list[dict]:
    """The claims told on MIN_SHOWS or more shows, or by as many callers: versions of one claim grouped the way
    what people post is (app/narratives.groups: mutual neighbours alike enough), each group as the version nearest its
    center, with who told it. One show's one-off take isn't folklore; told again elsewhere, it is."""
    from collections import Counter

    import numpy as np

    from app.narratives import embed, groups
    store = store if store is not None else load()
    rows = [dict(c, show=e['show'], url=url, date=e['date'], lean=e.get('lean')) for url, e in store.items() for c in e['claims']]
    if len(rows) < 2:
        return []
    out = []
    for g in groups([{'text': r['claim']} for r in rows]):
        tellers = [rows[i] for i in g]
        shows = {r['show'] for r in tellers}
        callers = {(r['url'], r['at']) for r in tellers if r.get('speaker') == 'caller'}
        if len(shows) < MIN_SHOWS and len(callers) < MIN_SHOWS:
            continue
        v = embed([r['claim'] for r in tellers])
        lead = tellers[int(np.argmax(v @ v.mean(0)))]
        out.append({'claim': lead['claim'], 'shows': sorted(shows), 'tellings': len(tellers),
                    'leans': dict(Counter(r['lean'] or '' for r in tellers)), 'speakers': dict(Counter(r['speaker'] or '' for r in tellers)),
                    'date': max(r['date'] for r in tellers), 'ref': lead['url'],
                    'told': [{'show': r['show'], 'url': r['url'], 'at': r['at'], 'speaker': r['speaker'], 'claim': r['claim'],
                              'quote': r['quote']} for r in tellers]})
    return sorted(out, key=lambda r: -len(r['shows']))


def claims() -> list[dict]:
    """The retold claims, for the motif index's filing (source SOURCE; the first episode that told it as its ref)"""
    return [{'claim': r['claim'], 'source': SOURCE, 'ref': r['ref'], 'date': r['date']} for r in retold()]


def backlog() -> dict:
    """How far behind the reading is: episodes and parts not read yet"""
    store = load()
    eps = episodes()
    left = [(ep, len(ep['chunks']) - store.get(ep['url'], {}).get('read', 0)) for ep in eps]
    return {'episodes': len(eps), 'unread episodes': sum(1 for _, n in left if n > 0), 'unread parts': sum(n for _, n in left if n > 0)}
