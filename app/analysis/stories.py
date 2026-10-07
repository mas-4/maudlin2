"""Stories are clusters that persist across runs. Matching each run's clusters back to the stories they
continue lets us label a story once, and compare how each outlet covers the same event: an outlet whose
headlines run more negative than everyone else's on the same stories is framing, not just reporting bad news."""
import hashlib
import json
import os
import re
from collections import Counter
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz
from sqlalchemy import func, update

from app.analysis import llm
from app.models import Session, SqlLock, Saga, Story, StoryHeadline, StorySnapshot, Headline, Article, Agency
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

# Relabel a story once its coverage has grown this much, since early labels come from the first few outlets
RELABEL_GROWTH = 2
MAX_LABELS_PER_RUN = 25
FRAMING_WINDOW_DAYS = 30
MIN_STORIES_FOR_FRAMING = 5


def headline_sentiment(df: pd.DataFrame) -> pd.Series:
    """How good or bad each headline makes the news look, on roughly -1 to 1: the llm's event score (-2 to 2,
    halved) where there is one, else the VADER/AFINN blend the site used before."""
    legacy = (df['afinn'] + df['vader_compound']) / 2
    if 'event_score' not in df:
        return legacy
    return (df['event_score'] / 2).fillna(legacy)


def refresh_story_sentiment():
    """Recompute every saved story member's sentiment and deviation from the headlines' current scores, e.g.
    after the headlines were rescored with a new rubric."""
    with Session() as s, SqlLock:
        rows = s.query(StoryHeadline.id, StoryHeadline.story_id, Headline.afinn, Headline.vader_compound,
                       Headline.event_score).join(Headline, Headline.id == StoryHeadline.headline_id).all()
        df = pd.DataFrame(rows, columns=['id', 'story_id', 'afinn', 'vader_compound', 'event_score'])
        if df.empty:
            return
        df['sentiment'] = headline_sentiment(df)
        df['deviation'] = df['sentiment'] - df.groupby('story_id')['sentiment'].transform('mean')
        s.execute(update(StoryHeadline), df[['id', 'sentiment', 'deviation']].to_dict(orient='records'))
        s.commit()
    logger.info("Refreshed sentiment for %d story headlines", len(df))


# A story can leave the front pages and come back hours later under fresh headlines, none of them the ones it had, so
# matching by shared headlines starts a new story for it: Oct 6, the physics Nobel was on one run at noon, gone, and
# back at 5 PM as a second story, then a saga of two near-identical parts. A cluster that continues no story is
# compared with the stories that left the front pages in the last RETURN_WINDOW; one sharing RETURN_WORDS of its
# frequent words is put to the bigger model: the same news event told again, or a different one? (Two games of one
# playoff series share nearly every word and are different events.) The same event continues the old story.
RETURN_WINDOW = td(hours=48)
RETURN_GAP = td(minutes=90)  # a story last seen longer ago than this has left the front pages
RETURN_WORDS = 2
RETURN_CANDIDATES = 2  # the most alike stories put to the model, the closest first
RETURN_MODEL = 'gemma4:26b'
RETURNS = os.path.join(Config.data, 'story_returns.json')  # the model's verdicts, by the headlines shown
MERGES = os.path.join(Config.data, 'story_merges.json')  # a story found to be another's return: {gone id: kept id}
STOP = {'that', 'this', 'with', 'from', 'after', 'over', 'into', 'about', 'what', 'says', 'said', 'will', 'more',
        'than', 'have', 'been', 'were', 'their', 'they', 'when', 'amid', 'year', 'news', 'live', 'updates', 'just'}
SAME_EVENT_PROMPT = """Two groups of news headlines. The first left the front pages some hours before the second \
appeared.

Earlier:
{a}

Now:
{b}

Are they the same news event: the same announcement, incident, game, ruling, death, award or report, told again \
(perhaps with more details, profiles or reactions)? A new development (the next game in a series, a new ruling or \
vote, an arrest after a crime, a resignation over it, a new attack) is a different event, even in the same running \
story. Go by what most headlines in each group report: a stray headline about something else doesn't change the answer.

reason: one sentence
verdict: "the same event" or "different events\""""
SAME_EVENT_SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string", "maxLength": 600},
    "verdict": {"type": "string", "enum": ["the same event", "different events"]}}, "required": ["reason", "verdict"]}


def frequent_words(titles: list[str], share: float = 0.3) -> set[str]:
    """Words (4+ letters, not stop words) in at least `share` of the headlines"""
    counts = Counter(w for t in titles for w in set(re.findall(r"[a-z][a-z']{3,}", t.lower())) - STOP)
    least = max(1, share * len(titles))
    return {w for w, n in counts.items() if n >= least}


def same_event(earlier: list[str], now: list[str]) -> bool | None:
    """The model's verdict on two groups of headlines (cached by the headlines shown); None without an answer"""
    a, b = [list(dict.fromkeys(t.strip() for t in ts))[:5] for ts in (earlier, now)]
    key = hashlib.sha1(json.dumps([SAME_EVENT_PROMPT, a, b]).encode()).hexdigest()  # a reworded prompt asks afresh
    cache = read_json(RETURNS, {})
    if key not in cache:
        answer = llm.complete_json(SAME_EVENT_PROMPT.format(a='\n'.join(f'- {t}' for t in a), b='\n'.join(f'- {t}' for t in b)),
                                   SAME_EVENT_SCHEMA, max_tokens=500, model=RETURN_MODEL)
        if not answer or answer.get('verdict') not in SAME_EVENT_SCHEMA['properties']['verdict']['enum']:
            return None
        cache[key] = {'same': answer['verdict'] == 'the same event', 'reason': answer.get('reason', ''), 'a': a, 'b': b,
                      'model': RETURN_MODEL}
        write_json(RETURNS, cache)
        logger.info("Story return? %s | %s -> %s (%s)", a[0], b[0], cache[key]['same'], cache[key]['reason'])
    return cache[key]['same']


def returning(s, titles: list[str], claimed: set[int], now: dt) -> Story | None:
    """The story that left the front pages lately and that these headlines (a cluster continuing no story) tell
    again, or None"""
    words = frequent_words(titles)
    if len(words) < RETURN_WORDS:
        return None
    rows = s.query(Story.id, Headline.title).join(StoryHeadline, StoryHeadline.story_id == Story.id) \
        .join(Headline, Headline.id == StoryHeadline.headline_id) \
        .filter(Story.last_seen >= now - RETURN_WINDOW, Story.last_seen < now - RETURN_GAP).all()
    theirs = {}
    for sid, title in rows:
        if sid not in claimed:
            theirs.setdefault(sid, []).append(title)
    alike = sorted(((len(words & frequent_words(ts)), sid) for sid, ts in theirs.items()), reverse=True)
    for shared, sid in alike[:RETURN_CANDIDATES]:
        if shared >= RETURN_WORDS and same_event(theirs[sid], titles):
            return s.get(Story, sid)
    return None


def merges() -> dict[int, int]:
    """{gone story id: the story it was merged into}, followed to the end of any chain"""
    raw = {int(k): int(v['into']) for k, v in read_json(MERGES, {}).items()}
    out = {}
    for k in raw:
        v, seen = raw[k], {k}
        while v in raw and v not in seen:
            seen.add(v)
            v = raw[v]
        out[k] = v
    return out


def merge_stories(keep: int, gone: int, why: str = ''):
    """Fold story `gone` into story `keep` (by hand, or a return the model missed): its headlines and snapshots move,
    its span joins keep's, and its id is remembered (MERGES), so its page redirects and data keyed by it follow"""
    with Session() as s, SqlLock:
        a, b = s.get(Story, keep), s.get(Story, gone)
        moved = [i for (i,) in s.query(StoryHeadline.headline_id).filter(StoryHeadline.story_id == gone)]
        s.query(StoryHeadline).filter(StoryHeadline.story_id == gone).update({'story_id': keep})
        s.query(StorySnapshot).filter(StorySnapshot.story_id == gone).update({'story_id': keep})
        a.first_seen, a.last_seen = min(a.first_seen, b.first_seen), max(a.last_seen, b.last_seen)
        a.saga_id = a.saga_id or b.saga_id
        record = {'into': keep, 'label': b.label, 'first_seen': b.first_seen.isoformat(), 'headlines': moved,
                  'at': dt.now(pytz.UTC).isoformat(timespec='seconds'), 'why': why}
        s.delete(b)
        s.flush()
        if a.saga_id and s.query(Story).filter(Story.saga_id == a.saga_id).count() < 2:  # a saga of one is no saga
            saga = a.saga_id
            a.saga_id = None
            s.query(Saga).filter(Saga.id == saga).delete()
        s.commit()
    done = read_json(MERGES, {})
    done[str(gone)] = record
    write_json(MERGES, done)
    logger.info("Merged story %d into %d (%d headlines)", gone, keep, len(moved))


def sync_stories(df: pd.DataFrame) -> dict[int, Story]:
    """Map each cluster in `df` (one headline per outlet, with a `cluster` and `headline_id` column) to a
    persisted story, recording every headline's deviation from its story's mean sentiment."""
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    stories = {}
    claimed = set()  # stories already continued by a cluster in this run
    with Session() as s, SqlLock:
        # Biggest clusters first, so when one story's coverage splits into two clusters this hour, the bigger part
        # keeps the story (and its title) and the smaller becomes a story of its own, instead of both showing as
        # cards with the same title
        groups = sorted(df.groupby('cluster'), key=lambda item: -len(item[1]))
        for cluster, group in groups:
            ids = [int(i) for i in group['headline_id']]
            # The story that already holds most of these headlines is the one this cluster continues
            matches = s.query(StoryHeadline.story_id, func.count().label('n')).filter(
                StoryHeadline.headline_id.in_(ids)
            ).group_by(StoryHeadline.story_id).order_by(func.count().desc()).all()
            match = next((m for m in matches if m.story_id not in claimed), None)
            if match:
                story = s.get(Story, match.story_id)
            elif (back := returning(s, group['title'].tolist() if 'title' in group else
                                    [t for (t,) in s.query(Headline.title).filter(Headline.id.in_(ids))],
                                    claimed, now)) is not None:
                story = back  # a story back on the front pages under new headlines
            else:
                story = Story(first_seen=now, last_seen=now)
                s.add(story)
                s.flush()
            story.last_seen = now

            sentiment = headline_sentiment(group)
            mean = sentiment.mean()
            existing = {sh.headline_id: sh for sh in s.query(StoryHeadline).filter(StoryHeadline.headline_id.in_(ids))}
            for headline_id, value in zip(ids, sentiment):
                member = existing.get(headline_id) or StoryHeadline(headline_id=headline_id)
                member.story_id = story.id  # a headline can move to the story it now clusters with
                member.sentiment = float(value)
                member.deviation = float(value - mean)
                member.last_seen = now
                s.add(member)
            stories[cluster] = story
            claimed.add(story.id)
        s.commit()
        for story in stories.values():
            s.refresh(story)
        s.expunge_all()
    logger.info("Synced %d clusters to stories", len(stories))
    return stories


LABEL_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}

LABEL_PROMPT = """These headlines from different news outlets all cover the same news event:

{headlines}

Write a short, neutral title (4 to 10 words) that states what happened. Use plain factual language a wire \
service would use: no outlet names, no loaded or emotive words, no opinion, and don't adopt any one \
outlet's framing. Write it in sentence case: capitalize only the first word and proper nouns.

Examples of the style:
- Senate passes stopgap bill to avert government shutdown
- Earthquake of magnitude 6.1 strikes central Japan
- Federal judge blocks Texas immigration law"""


def restore_case(label: str, headlines) -> str:
    """Small models drift on capitalization ("doj", "U.s.", "cornell"). The outlets' own headlines spell proper
    nouns and acronyms right, so each word takes the casing the headlines mostly use for it mid-sentence, and the
    title starts with a capital."""
    spellings: dict[str, Counter] = {}
    for headline in headlines:
        words = re.findall(r"[\w.'-]+", headline)
        long_words = [w for w in words if len(w) > 3]
        if long_words and sum(w[0].isupper() for w in long_words) / len(long_words) > 0.6:
            continue  # Title Case headlines capitalize everything, so they say nothing about proper nouns
        for i, word in enumerate(words):
            if i == 0 and word == word.capitalize():
                continue  # a headline's first word is capitalized anyway, unless it's an acronym like DOJ
            spellings.setdefault(word.lower(), Counter())[word] += 1

    def fix(match):
        word = match.group()
        if re.fullmatch(r'(\w\.){2,}', word):
            return word.upper()  # dotted abbreviations: U.S., D.C.
        seen = spellings.get(word.lower())
        return seen.most_common(1)[0][0] if seen else word

    label = re.sub(r"[\w.'-]+", fix, label)
    return label[0].upper() + label[1:]


def label_stories(df: pd.DataFrame, stories: dict[int, Story]) -> dict[int, str]:
    """Write a neutral title for stories that are new or have grown a lot since they were labeled. Returns
    cluster -> label for every story that has one, so callers can fall back to a headline for the rest."""
    labels = {cluster: story.label for cluster, story in stories.items() if story.label}
    if llm.backend() is None:
        return labels

    outlets = df.groupby('cluster')['agency'].nunique()
    todo = [cluster for cluster, story in stories.items()
            if not story.label or outlets[cluster] >= RELABEL_GROWTH * (story.labeled_with or 0)]
    for cluster in todo[:MAX_LABELS_PER_RUN]:
        headlines = '\n'.join(f'- {title}' for title in df[df['cluster'] == cluster]['title'])
        result = llm.complete_json(LABEL_PROMPT.format(headlines=headlines), LABEL_SCHEMA, max_tokens=64)
        label = (result or {}).get('title', '').strip().rstrip('.')
        if not label:
            continue
        label = restore_case(label, df[df['cluster'] == cluster]['title'])
        with Session() as s, SqlLock:
            story = s.get(Story, stories[cluster].id)
            story.label = label
            story.labeled_with = int(outlets[cluster])
            s.commit()
        labels[cluster] = label
    return labels


def framing_scores() -> pd.DataFrame:
    """Each outlet's average deviation from the other outlets covering the same stories, over the last month.
    Negative means its headlines run gloomier than the rest of the coverage of the same events."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=FRAMING_WINDOW_DAYS)
    with Session() as s:
        rows = s.query(
            Agency.name, Agency._bias, StoryHeadline.deviation, StoryHeadline.story_id  # noqa prot attr
        ).join(Headline, Headline.id == StoryHeadline.headline_id).join(Headline.article).join(Article.agency).filter(
            StoryHeadline.last_seen > since
        ).all()
    df = pd.DataFrame(rows, columns=['agency', 'bias', 'deviation', 'story_id'])
    if df.empty:
        return df
    scores = df.groupby(['agency', 'bias']).agg(
        framing=('deviation', 'mean'), stories=('story_id', 'nunique')
    ).reset_index()
    return scores[scores['stories'] >= MIN_STORIES_FOR_FRAMING].sort_values('framing')


MIN_HEADLINES_FOR_LOADED = 30


def loaded_language() -> pd.DataFrame:
    """Each outlet's average loaded score (0 plain to 2 built to provoke) over its news headlines this month."""
    since = dt.now(pytz.UTC).replace(tzinfo=None) - td(days=FRAMING_WINDOW_DAYS)
    with Session() as s:
        rows = s.query(Agency.name, Agency._bias, Headline.loaded_score).join(  # noqa prot attr
            Headline.article).join(Article.agency).filter(
            Headline.first_accessed > since, Headline.loaded_score.isnot(None), Headline.news_score >= 0.5
        ).all()
    df = pd.DataFrame(rows, columns=['agency', 'bias', 'loaded'])
    if df.empty:
        return df
    scores = df.groupby(['agency', 'bias']).agg(loaded=('loaded', 'mean'), headlines=('loaded', 'size')).reset_index()
    return scores[scores['headlines'] >= MIN_HEADLINES_FOR_LOADED].sort_values('loaded')
