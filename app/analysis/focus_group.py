"""What voters say in The Bulwark's The Focus Group (#164): the recorded focus groups of voters its episodes play and
discuss, read for the stories and beliefs the voters tell. A source of its own beside what people post online
(app/narratives.py) and what fact-checkers examine: its claims are filed in our motif index like theirs, so a motif
heard in a focus group and told online is one entry seen from two sides.

The transcripts (app/transcribe.py) have no speaker names and carry ads; the bigger local model reads each episode
in chunks and keeps only what the voters say. Quotes are kept for the local checker pages; the site shows the claims
in our words, never the quotes (as with posts)."""
import json
import os
import re
import time

from app.analysis import llm
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

STORE = os.path.join(Config.data, 'focus_group_claims.json')  # episode url -> its claims, filled chunk by chunk
MODEL = 'qwen3:30b-a3b'
CHUNK = 6000  # characters of transcript a call
SOURCE = 'Focus Group'
FOUND = 0.6  # a quote counts as the voter's words if this share of its four-word runs is in the transcript part
SAME_QUOTE = 0.6  # two quotes sharing this share of the shorter one's runs are one quote
PROMPT = """This is part of an episode of a podcast ({title}) that plays recordings of focus groups of voters and has \
its hosts and guests discuss them. The transcript has no speaker names and may include ads.

{text}

List the stories, beliefs and claims about politics and public life that the VOTERS in the focus groups tell in this \
part: what they believe is true, why they think things happen, what they say someone is like, stories they have heard. \
Not wishes or plans ("I want gas prices to go down", "I'm not voting for him"), not what the hosts or guests say in \
their analysis, not ads. For each:
claim: one plain sentence, the way the voter tells it: what they say is true or believe
quote: the voter's own words, at most 25 words, copied from the transcript
side: the voter as the episode presents them ("Trump voter", "Biden voter", "swing voter", "Democrat", "Republican"), \
or "" if unclear
Most parts have none to three; give none for a part with only hosts, ads or small talk.

reason: a sentence on who is speaking in this part"""
SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string", "maxLength": 400},
    "claims": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
        "claim": {"type": "string", "maxLength": 240}, "quote": {"type": "string", "maxLength": 240},
        "side": {"type": "string", "maxLength": 40}}, "required": ["claim", "quote", "side"]}}},
    "required": ["reason", "claims"]}


def load() -> dict:
    return read_json(STORE, {})


def save(store: dict):
    write_json(STORE, store, indent=1)


def episodes() -> list[dict]:
    """Every transcribed episode, newest first, with its transcript cut into CHUNK-sized parts."""
    from app.models import Session, SideItem, SideTranscript
    with Session() as s:
        rows = s.query(SideItem.title, SideItem.url, SideItem.published, SideTranscript.segments).join(
            SideTranscript, SideTranscript.item_id == SideItem.id).filter(SideItem.source == 'focusgroup').order_by(
            SideItem.published.desc()).all()
    out = []
    for title, url, published, segments in rows:
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
        out.append({'title': title, 'url': url, 'date': str(published)[:10], 'chunks': chunks})
    return out


CONTRACTIONS = [("n't", ' not'), ("'re", ' are'), ("'m", ' am'), ("'ll", ' will'), ("'ve", ' have'), ("'d", ' would'),
                ("'s", ' is')]  # 's as 'is' even where it's a possessive: both sides are read alike


def runs(text: str, n: int = 4) -> set[tuple]:
    """A text's runs of n words (all of it, for a shorter text)"""
    text = text.lower().replace('’', "'")
    for short, full in CONTRACTIONS:  # the model sometimes writes out what the voter said short ("it's", "it is")
        text = text.replace(short, full)
    words = re.findall(r"[a-z0-9]+", text)
    n = min(n, len(words))
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)} if n else set()


def checked(claims: list[dict], text: str) -> tuple[list[dict], list[dict]]:
    """(kept, dropped) of a transcript part's claims. Kept only if the quote is in the transcript (the model sometimes
    paraphrased, or quoted a host) and isn't mostly an earlier claim's quote (once it paired 'Amy Acton is not
    credible due to negative ads' with a quote about Vivek Ramaswamy, the one it had just used)."""
    spoken, kept, dropped = runs(text), [], []
    for c in claims:
        q = runs(c['quote'])
        if not q or len(q & spoken) / len(q) < FOUND:
            dropped.append(dict(c, why='quote not in the transcript'))
        elif any(len(q & runs(k['quote'])) / min(len(q), len(runs(k['quote'])) or 1) >= SAME_QUOTE for k in kept):
            dropped.append(dict(c, why='quote already used for another claim'))
        else:
            kept.append(c)
    return kept, dropped


def extract(budget: float | None = None) -> dict:
    """Read the episodes not read yet, newest first, chunk by chunk, saving as it goes, for at most `budget`
    seconds (the next run carries on)."""
    store = load()
    if llm.backend() is None:
        return store
    started, calls = time.time(), 0
    for ep in episodes():
        entry = store.setdefault(ep['url'], {'title': ep['title'], 'date': ep['date'], 'read': 0, 'claims': []})
        while entry['read'] < len(ep['chunks']):
            if budget is not None and time.time() - started > budget:
                logger.info("Focus Group: %d chunks read this run; more next run", calls)
                return store
            chunk = ep['chunks'][entry['read']]
            answer = llm.complete_json(PROMPT.format(title=ep['title'], text=chunk['text']), SCHEMA, max_tokens=900,
                                       model=MODEL)
            found = []
            for c in (answer or {}).get('claims', []):
                claim = ' '.join(c.get('claim', '').split())
                if sum(ch.isalpha() for ch in claim) < 12:  # '...' and other empty fills
                    continue
                side = c.get('side', '').split('(')[0].strip()  # 'Trump voter (implied by context...)'
                found.append({'claim': claim, 'quote': c.get('quote', '').strip(), 'side': side, 'at': round(chunk['at'])})
            kept, dropped = checked(found, chunk['text'])
            entry['claims'] += kept
            entry.setdefault('dropped', []).extend(dropped)
            entry['read'] += 1
            entry['chunks'] = len(ep['chunks'])
            calls += 1
            save(store)
    if calls:
        logger.info("Focus Group: %d chunks read; %d claims from %d episodes", calls,
                    sum(len(e['claims']) for e in store.values()), len(store))
    return store


def recheck() -> list[str]:
    """Check the claims read before the quote check (Oct 5) the same way, part by part; the dropped ones move to
    'dropped' with the reason. Returns the dropped claims, to take out of the motif index."""
    store, gone = load(), []
    for ep in episodes():
        entry = store.get(ep['url'])
        if not entry:
            continue
        kept = []
        for chunk in ep['chunks']:
            part = [c for c in entry['claims'] if c.get('at') == round(chunk['at'])]
            ok, dropped = checked(part, chunk['text'])
            kept += ok
            entry.setdefault('dropped', []).extend(dropped)
            gone += [c['claim'] for c in dropped]
        kept += [c for c in entry['claims'] if c.get('at') not in {round(ch['at']) for ch in ep['chunks']}]
        entry['claims'] = kept
    save(store)
    return gone


def claims() -> list[dict]:
    """Every voter claim read so far, for the motif index's filing (source SOURCE, the episode as its ref)."""
    return [{'claim': c['claim'], 'source': SOURCE, 'ref': url, 'date': e['date'], 'side': c.get('side') or None}
            for url, e in load().items() for c in e['claims']]
