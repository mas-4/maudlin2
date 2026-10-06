"""The running order of the hourly radio newscasts (#159): NPR News Now and ABC News Update, each split into its
stories in the order they aired, every story matched to the front pages' stories, so a newscast's lead can be set
beside what the front pages led with at that hour.

The transcripts come from app/transcribe.py. The bigger local model splits each newscast into stories (sign-offs
alone miss transitions) and says which of that hour's front-page stories each one is, if any. Kept in RUNNING
(newscast url -> its order), read once per newscast."""
import os
import re
import time
from datetime import timedelta

from app.analysis import llm
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

RUNNING = os.path.join(Config.data, 'running_order.json')
SOURCES = {'nprnewsnow': 'NPR News Now', 'abcupdate': 'ABC News Update'}
# Gemma 4 26B since Oct 6: on 10 newscasts its stories passed the first-words check 96% of the time (Qwen3 30B-A3B 81%),
# with nearly the same front-page picks, and a little faster (docs/models.md)
MODEL = 'gemma4:26b'
DAYS = 3  # newscasts this recent are read
NEAR = timedelta(minutes=50)  # the front-page run this close to a newscast is its hour's
FRONT = 40  # the front pages' biggest stories at that hour, offered to the model to match
PROMPT = """This is the transcript of a short radio newscast ({show}):

{text}

These were the stories on the news sites' front pages at that hour, numbered:
{front}

Split the newscast into the news stories it covers, in the order they aired. Leave out the show's opening and \
closing and the weather unless it is news. For each part:
kind: "news" for a news story; "ad or promo" for a sponsor message, an advertisement, or a promotion of a show, \
a product or a business. A trailer for a TV series, film or streaming service ("streaming October 14th, only on \
Disney+") is a promo, not news. Ads often come before the anchor's "I'm ..." and after the closing "This is ABC News".
title: a short neutral headline for it (at most 12 words)
first_words: the first five or six words of the part, copied exactly from the transcript
front: the number of the front-page story that is the same news event, or 0 if none is (same event, not just the \
same topic)"""
SCHEMA = {"type": "object", "properties": {"stories": {"type": "array", "maxItems": 14, "items": {
    "type": "object", "properties": {"kind": {"type": "string", "enum": ["news", "ad or promo"]},
                                     "title": {"type": "string", "maxLength": 120},
                                     "first_words": {"type": "string", "maxLength": 80},
                                     "front": {"type": "integer"}},
    "required": ["kind", "title", "first_words", "front"]}}}, "required": ["stories"]}


def load() -> dict:
    return read_json(RUNNING, {})


def save(store: dict):
    write_json(RUNNING, store, indent=1)


def newscasts() -> list[dict]:
    """Transcribed newscasts from the last DAYS, newest first"""
    from datetime import datetime
    from app.models import Session, SideItem, SideTranscript
    since = datetime.utcnow() - timedelta(days=DAYS)
    with Session() as s:
        rows = s.query(SideItem.source, SideItem.title, SideItem.url, SideItem.published, SideTranscript.text).join(
            SideTranscript, SideTranscript.item_id == SideItem.id).filter(
            SideItem.source.in_(list(SOURCES)), SideItem.published >= since).order_by(SideItem.published.desc()).all()
    return [{'source': src, 'title': title, 'url': url, 'published': published, 'text': text or ''}
            for src, title, url, published, text in rows]


def stories_at(when) -> list[dict]:
    """The front pages' stories at the run nearest a time (within NEAR), biggest first: how many outlets had each
    on their front pages then (the story snapshots each run keeps)"""
    from app.models import Session, Story, StorySnapshot
    with Session() as s:
        runs = [r for (r,) in s.query(StorySnapshot.at).filter(
            StorySnapshot.at.between(when - NEAR, when + NEAR)).distinct()]
        if not runs:
            return []
        run = min(runs, key=lambda r: abs(r - when))
        rows = s.query(Story.id, Story.label, StorySnapshot.outlets).join(StorySnapshot, StorySnapshot.story_id == Story.id).filter(
            StorySnapshot.at == run).all()
    return sorted([{'id': i, 'label': label or '', 'outlets': n} for i, label, n in rows if label],
                  key=lambda r: -r['outlets'])


ABC_OPEN = re.compile(r"\b(?:ABC|NBC) News[.,]? I'm [A-Z]")  # 'ABC News. I'm Mike Dubuski' (NBC: a mishearing)
ABC_CLOSE = 'This is ABC News'


def newscast_only(source: str, text: str) -> str:
    """ABC News Update wraps each newscast in ads: a promo before the anchor's 'ABC News, I'm ...' and a sponsor read
    after 'This is ABC News'. Cut them off by that fixed pattern (the model's own ad calls were unsteady: one run kept
    a Disney+ trailer as news, the next dropped the lead story as an ad)."""
    if source != 'abcupdate':
        return text
    start = ABC_OPEN.search(text[:1200])
    if start:
        text = text[start.start():]
    end = text.rfind(ABC_CLOSE)
    return text[:end] if end > len(text) * 0.4 else text


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def said(first_words: str, spoken: list[str], after: int = -1) -> int | None:
    """Where a part's first words were spoken in the newscast, after the previous part's (its first three words in a
    row in the transcript), or None. A part the model made up has no such place: once it copied the front-page list
    as the newscast, reusing one real opening for every made-up story."""
    head = words(first_words)[:3]
    if not head:
        return None
    return next((i for i in range(after + 1, len(spoken)) if spoken[i:i + len(head)] == head), None)


def read(budget: float | None = None) -> dict:
    """Split and match the newscasts not read yet, newest first, for at most `budget` seconds (the next run carries
    on). A newscast with no front-page run near it waits."""
    store = load()
    if llm.backend() is None:
        return store
    started, done = time.time(), 0
    for cast in newscasts():
        if cast['url'] in store or len(cast['text']) < 200:
            continue
        if budget is not None and time.time() - started > budget:
            break
        front = stories_at(cast['published'])[:FRONT]
        if not front:
            continue
        listing = '\n'.join(f"{n}. {f['label']}" for n, f in enumerate(front, 1))
        text = newscast_only(cast['source'], cast['text'])
        answer = llm.complete_json(PROMPT.format(show=SOURCES[cast['source']], text=text[:7000], front=listing),
                                   SCHEMA, max_tokens=1500, model=MODEL)
        if answer is None:
            continue
        items, spoken, at = [], words(text), -1
        for x in answer.get('stories', []):
            title = ' '.join(x.get('title', '').split())
            where = said(x.get('first_words', ''), spoken, at)
            if where is None:
                continue
            at = where
            if not title or x.get('kind') != 'news':
                continue
            item = {'title': title}
            n = x.get('front') or 0
            if 1 <= n <= len(front):
                item.update(story=front[n - 1]['id'], story_label=front[n - 1]['label'], front_rank=n,
                            outlets=front[n - 1]['outlets'])
            if item.get('story') and any(x.get('story') == item['story'] for x in items):
                continue  # the same story again (the anchor's lead-in, then the reporter): kept where it first aired
            items.append(item)
        store[cast['url']] = {'source': cast['source'], 'show': SOURCES[cast['source']], 'title': cast['title'],
                              'published': cast['published'].isoformat(timespec='minutes'), 'items': items,
                              'front_top': front[:5]}
        done += 1
        save(store)
    if done:
        logger.info("Running order: %d newscasts read (%d in all)", done, len(store))
    return store
