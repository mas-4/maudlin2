"""Stories are clusters that persist across runs. Matching each run's clusters back to the stories they
continue lets us label a story once, and compare how each outlet covers the same event: an outlet whose
headlines run more negative than everyone else's on the same stories is framing, not just reporting bad news."""
import hashlib
import json
import os
import re
from collections import Counter, namedtuple
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz
from sqlalchemy import func, update

from app.analysis import llm
from app.models import Session, SqlLock, Saga, Story, StoryHeadline, StorySnapshot, Headline, Article, Agency
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json
from app.analysis import local_models

logger = get_logger(__name__)

# Relabel a story once its coverage has grown this much, since early labels come from the first few outlets
RELABEL_GROWTH = 2
# A live story's label is written again once it's this old and new headlines have come in since: a story is kept for
# days and its news moves on, but its outlet count rarely doubles (Oct 11: "Tennessee inmate survives botched
# execution attempt" from Oct 2 stood over nine days of Christa Pike headlines, by then about her leaving hospital;
# "Trump announces diesel deal with Putin" over his call for Ukraine to replace Zelensky)
RELABEL_AGE = td(hours=12)
LABEL_FROM = 30  # the newest headlines the label is written from
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
RETURN_MODEL = local_models.BIG
RETURNS = os.path.join(Config.data, 'story_returns.json')  # the model's verdicts, by the headlines shown
MERGES = os.path.join(Config.data, 'story_merges.json')  # a story found to be another's return: {gone id: kept id}
LABELED_AT = os.path.join(Config.data, 'story_labeled_at.json')  # story id -> when its label was written (ISO)
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
# One running story can split in two for an hour's clustering while both parts are on the front pages (the bigger
# keeps the story, the smaller starts a new one), and the two clusters join again later. The joined cluster then
# continues whichever part holds more of its headlines, often the young one, and the older story ends there: Oct 13,
# eleven days of Christa Pike ended at 7 AM and "discharged from hospital", split off at 1 AM, carried on, both parts
# holding the same discharge headlines from Oct 10. A cluster holding headlines of two stories both live lately, the
# lesser at least REJOIN_LEAST of them and REJOIN_SHARE of the cluster, is put to the model with this prompt: the same
# event, and the older continues with the younger folded into it (merge_stories).
REJOIN_LEAST = 3
REJOIN_SHARE = 0.2
REJOIN_PROMPT = SAME_EVENT_PROMPT.replace('The first left the front pages some hours before the second appeared.',
                                          'Both were on the front pages at the same time.') \
    .replace('Earlier:', 'One:').replace('Now:', 'The other:')
# A story kept for days absorbs every new development under a moving title (Oct 15, the person): the Fort Hood
# shooter's story ran ten days, from Trump approving a firing squad through the livestream plan and its backlash to
# "Trump cancels livestream of Fort Hood shooter's execution", 368 headlines in one part while the smaller developments
# split off as parts of their own. So when a titled live story is due a new title, its news moved on (RELABEL_AGE) or
# its coverage doubled (the cancellation took Fort Hood from 6 outlets to 35 in an hour: a big development comes as a
# burst), the model is asked whether its newest headlines (those since its last title) report a new development or the
# same event told again: a new development starts a new story in the same saga, and the old story keeps the headlines
# up to its last title and ends (label_ended titles it once more). A story due when a run's questions are spent waits
# for the next run's, title and all, so no development passes unasked. Off until the replay (Sinbad: ~/maudlin-data/papers
# /sinbad.md, scripts/experiments/s5_sinbad.py) and the person's verdicts on it.
SPLIT_DEVELOPMENTS = False
SPLIT_LEAST = 3  # headlines on each side of a split, at least
MAX_SPLIT_CHECKS = 5  # questions a run asks, at most (one per titled story due a new title, SPLIT_LEAST a side)
SPLITS = os.path.join(Config.data, 'story_splits.json')  # {ended story id: {'into': new story id, 'at', ...}}
SPLIT_PROMPT = SAME_EVENT_PROMPT.replace(
    'Two groups of news headlines. The first left the front pages some hours before the second appeared.',
    'Two groups of headlines from one running news story: its earlier headlines, and its newest, from the last \
twelve hours or so.').replace('Now:', 'Newest:')
SAME_EVENT_SCHEMA = {"type": "object", "properties": {
    "reason": {"type": "string", "maxLength": 600},
    "verdict": {"type": "string", "enum": ["the same event", "different events"]}}, "required": ["reason", "verdict"]}


def frequent_words(titles: list[str], share: float = 0.3) -> set[str]:
    """Words (4+ letters, not stop words) in at least `share` of the headlines"""
    counts = Counter(w for t in titles for w in set(re.findall(r"[a-z][a-z']{3,}", t.lower())) - STOP)
    least = max(1, share * len(titles))
    return {w for w, n in counts.items() if n >= least}


def same_event(earlier: list[str], now: list[str], prompt: str = SAME_EVENT_PROMPT) -> bool | None:
    """The model's verdict on two groups of headlines (cached by the headlines shown); None without an answer"""
    a, b = [list(dict.fromkeys(t.strip() for t in ts))[:5] for ts in (earlier, now)]
    key = hashlib.sha1(json.dumps([prompt, a, b]).encode()).hexdigest()  # a reworded prompt asks afresh
    cache = read_json(RETURNS, {})
    if key not in cache:
        answer = llm.complete_json(prompt.format(a='\n'.join(f'- {t}' for t in a), b='\n'.join(f'- {t}' for t in b)),
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
    ended = splits()  # a story ended at a new development returns as the story its news went on in, if at all
    for sid, title in rows:
        if sid not in claimed and sid not in ended:
            theirs.setdefault(sid, []).append(title)
    alike = sorted(((len(words & frequent_words(ts)), sid) for sid, ts in theirs.items()), reverse=True)
    for shared, sid in alike[:RETURN_CANDIDATES]:
        if shared >= RETURN_WORDS and same_event(theirs[sid], titles):
            return s.get(Story, sid)
    return None


Match = namedtuple('Match', 'story_id n')


# One story's coverage can split into two clusters in one hour where the smaller part shares no headline with the story
# (new wording from other outlets), so it matches nothing; it's no return either, since the story is still on the front
# pages; and if the two parts never land in one cluster again, nothing rejoins them (Oct 28, saga 99: "RFK Jr faces
# backlash for anti-Arab remarks" from 2 AM, and at noon "RFK Jr. faces backlash over anti-Arab remarks" started a
# story of its own, while the first ran out; the person: "this saga has 2 stories that are the same"). So a cluster
# that would start a new story is first compared with the stories this run's other clusters continue, by frequent words
# and then by the model (REJOIN_PROMPT); the same event continues that story, and the page folds the two clusters into
# one card (fold_twins).
def twin(titles: list[str], continued: dict[int, tuple[Story, list[str], object]], root=None) -> Story | None:
    """The story another cluster of this run continues that these headlines (a cluster continuing no story) tell
    too, or None. Never one whose cluster this run's seam cut parted from this one (the same `root`): the model,
    asked both ways, has just called them two events (clustering.split_seams)"""
    words = frequent_words(titles)
    if len(words) < RETURN_WORDS:
        return None
    alike = sorted(((len(words & frequent_words(ts)), sid) for sid, (_, ts, r) in continued.items()
                    if root is None or r is None or r != root), reverse=True)
    for shared, sid in alike[:RETURN_CANDIDATES]:
        if shared >= RETURN_WORDS and same_event(continued[sid][1], titles, prompt=REJOIN_PROMPT):
            return continued[sid][0]
    return None


def fold_twins(df: pd.DataFrame, stories: dict) -> tuple[pd.DataFrame, dict]:
    """Clusters that sync_stories mapped to one story (twin) folded into one, the first cluster's, keeping each
    outlet's headline from the first: one card per story"""
    first = {}
    rename = {}
    for cluster, story in stories.items():
        if story.id in first:
            rename[cluster] = first[story.id]
        else:
            first[story.id] = cluster
    if not rename:
        return df, stories
    df = df.copy()
    df['cluster'] = df['cluster'].replace(rename)
    if 'agency' in df:
        df = df.drop_duplicates(['cluster', 'agency'], keep='first')
    return df, {c: s for c, s in stories.items() if c not in rename}


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
            from app.analysis.sagas import record_end
            record_end(saga, {'story': keep})
        s.commit()
    done = read_json(MERGES, {})
    done[str(gone)] = record
    write_json(MERGES, done)
    logger.info("Merged story %d into %d (%d headlines)", gone, keep, len(moved))


def splits() -> dict[int, int]:
    """{story ended by a split: the story its newest headlines went on in}"""
    return {int(k): int(v['into']) for k, v in read_json(SPLITS, {}).items()}


def carried_on(sid: int, ended: dict[int, int]) -> int:
    """The story a split-ended story's news went on in, followed to the end of any chain"""
    seen = {sid}
    while sid in ended and ended[sid] not in seen:
        sid = ended[sid]
        seen.add(sid)
    return sid


def development_sides(sid: int, since: dt) -> tuple[list, list]:
    """Story `sid`'s headlines up to `since` (its last title) and after it, each newest first"""
    with Session() as s:
        rows = s.query(StoryHeadline.headline_id, Headline.title, Headline.first_accessed) \
            .join(Headline, Headline.id == StoryHeadline.headline_id).filter(StoryHeadline.story_id == sid) \
            .order_by(Headline.first_accessed.desc()).all()
    return [r for r in rows if r.first_accessed <= since], [r for r in rows if r.first_accessed > since]


def split_development(sid: int, since: dt, now: dt, sides: tuple[list, list] | None = None) -> Story | None:
    """The new story when story `sid`'s headlines first seen after `since` (its last title) report a new development,
    not the same event told again: they move to it, in the same saga (one is made for the two if the story had none),
    and the old story ends with its last kept headline. None when there's no split."""
    earlier, newest = sides or development_sides(sid, since)
    if min(len(newest), len(earlier)) < SPLIT_LEAST:
        return None
    if same_event([r.title for r in earlier], [r.title for r in newest], prompt=SPLIT_PROMPT) is not False:
        return None  # the same event told again, or no answer: the story goes on and is titled again
    moved = [r.headline_id for r in newest]
    with Session() as s, SqlLock:
        old = s.get(Story, sid)
        new = Story(first_seen=min(r.first_accessed for r in newest), last_seen=now, saga_id=old.saga_id)
        if old.saga_id is None:
            saga = Saga(first_seen=old.first_seen, last_seen=now)
            s.add(saga)
            s.flush()
            old.saga_id = new.saga_id = saga.id
        s.add(new)
        s.flush()
        s.query(StoryHeadline).filter(StoryHeadline.headline_id.in_(moved)).update({'story_id': new.id},
                                                                                   synchronize_session=False)
        # Off the front pages from its last kept headline: never put to the rejoin rule (both stories live), and
        # label_ended titles it once more from the headlines it kept
        old.last_seen = max(r.first_accessed for r in earlier)
        label = old.label
        s.commit()
        s.refresh(new)
        s.expunge(new)
    done = read_json(SPLITS, {})
    done[str(sid)] = {'into': new.id, 'label': label, 'since': since.isoformat(timespec='seconds'), 'headlines': moved,
                      'at': now.isoformat(timespec='seconds')}
    write_json(SPLITS, done)
    logger.info("Story %d split at a new development: %d headlines since %s went on as story %d (%s)", sid, len(moved),
                since, new.id, newest[0].title)
    return new


def rejoined(s, a: Story, b: Story, lesser: int, size: int, now: dt) -> tuple[Story, Story] | None:
    """(older, younger) when stories `a` and `b`, both on the front pages lately and both holding a fair part of one
    cluster (the lesser `lesser` of its `size` headlines), tell the same event: one story split and joined again"""
    if lesser < max(REJOIN_LEAST, REJOIN_SHARE * size) or min(a.last_seen, b.last_seen) < now - RETURN_GAP:
        return None
    older, younger = sorted((a, b), key=lambda x: x.first_seen)
    titles = [[t for (t,) in s.query(Headline.title).join(StoryHeadline, StoryHeadline.headline_id == Headline.id)
               .filter(StoryHeadline.story_id == x.id).order_by(Headline.first_accessed.desc()).limit(5)]
              for x in (older, younger)]
    if not all(titles) or not same_event(*titles, prompt=REJOIN_PROMPT):
        return None
    return older, younger


def sync_stories(df: pd.DataFrame) -> dict[int, Story]:
    """Map each cluster in `df` (one headline per outlet, with a `cluster` and `headline_id` column) to a
    persisted story, recording every headline's deviation from its story's mean sentiment."""
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    stories = {}
    claimed = set()  # stories already continued by a cluster in this run
    rejoins = []  # (kept, folded): one story split by an earlier hour's clustering, joined again now
    continued = {}  # story id -> (story, its cluster's titles, its seam root): this run's continued stories (twin)
    # A story ended at a new development is never continued: the story its news went on in is (followed through
    # merges too, should that one have been folded into another since)
    ended = splits()
    ended = {**merges(), **ended} if ended else {}
    with Session() as s, SqlLock:
        # Biggest clusters first, so when one story's coverage splits into two clusters this hour, the bigger part
        # keeps the story (and its title) and the smaller becomes a story of its own, instead of both showing as
        # cards with the same title
        groups = sorted(df.groupby('cluster'), key=lambda item: -len(item[1]))
        for cluster, group in groups:
            ids = [int(i) for i in group['headline_id']]
            titles = (group['title'].tolist() if 'title' in group else
                      [t for (t,) in s.query(Headline.title).filter(Headline.id.in_(ids))])
            # The story that already holds most of these headlines is the one this cluster continues
            matches = s.query(StoryHeadline.story_id, func.count().label('n')).filter(
                StoryHeadline.headline_id.in_(ids)
            ).group_by(StoryHeadline.story_id).order_by(func.count().desc()).all()
            if ended:  # its old headlines still on the front pages count for (but stay out of) the story it went on in
                n = Counter()
                for m in matches:
                    n[carried_on(m.story_id, ended)] += m.n
                matches = [Match(sid, k) for sid, k in n.most_common()]
            match = next((m for m in matches if m.story_id not in claimed), None)
            if match:
                story = s.get(Story, match.story_id)
                other = next((m for m in matches if m.story_id not in claimed and m.story_id != match.story_id), None)
                if other and (pair := rejoined(s, story, s.get(Story, other.story_id), other.n, len(ids), now)):
                    story = pair[0]
                    rejoins.append((pair[0].id, pair[1].id))
                    claimed.add(pair[1].id)  # folded in below: no other cluster continues it
            elif (back := returning(s, titles, claimed, now)) is not None:
                story = back  # a story back on the front pages under new headlines
            elif (same := twin(titles, continued, group['seam_root'].iloc[0] if 'seam_root' in group else None)) \
                    is not None:
                story = same  # this hour's clustering split the story: this part continues it too
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
                if member.story_id not in ended:  # what a split left with the old development stays there
                    member.story_id = story.id  # a headline can move to the story it now clusters with
                member.sentiment = float(value)
                member.deviation = float(value - mean)
                member.last_seen = now
                s.add(member)
            stories[cluster] = story
            claimed.add(story.id)
            continued.setdefault(story.id, (story, titles, group['seam_root'].iloc[0] if 'seam_root' in group else None))
        s.commit()
        for story in stories.values():
            s.refresh(story)
        s.expunge_all()
    for keep, gone in rejoins:
        merge_stories(keep, gone, 'one story split by an hour\'s clustering, joined again: the same event')
    logger.info("Synced %d clusters to stories", len(stories))
    return stories


LABEL_SCHEMA = {
    "type": "object",
    "properties": {"title": {"type": "string"}},
    "required": ["title"],
    "additionalProperties": False,
}

LABEL_PROMPT = """These headlines from different news outlets all cover the same news story, newest first:

{headlines}

Write a short, neutral title (4 to 10 words) that states what happened, its latest development if the story has \
moved on. Use plain factual language a wire \
service would use: no outlet names, no loaded or emotive words, no opinion, and don't adopt any one \
outlet's framing. Give people only the titles and roles the headlines give them. Go by what most of the headlines \
report, not a stray one. Write it in sentence case: capitalize only the first word and proper nouns.

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
    labeled_at = read_json(LABELED_AT, {})
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    # Each headline's first sighting, naive UTC as the stories table keeps its times. Not 'first_accessed': by now
    # that's display text ("Oct 9 4:04 PM"), and as text Oct 9 sorts after Oct 11, so no story ever looked to have
    # news newer than its label (Oct 11: the diesel deal's part kept its first title over two days of Zelensky news)
    seen = None
    if 'first_seen' in df:
        seen = pd.to_datetime(df['first_seen'])
        seen = seen.dt.tz_convert('UTC').dt.tz_localize(None) if seen.dt.tz is not None else seen
    newest = seen.groupby(df['cluster']).max() if seen is not None else None

    def written(story) -> pd.Timestamp:
        return pd.Timestamp(labeled_at.get(str(story.id)) or story.first_seen)

    def stale(cluster, story) -> bool:
        """Old, and headlines have come in since it was written (a story labeled before Oct 11 counts from its start)"""
        at = written(story)
        return newest is not None and now - at >= RELABEL_AGE and pd.Timestamp(newest[cluster]) > at

    def grown(cluster, story) -> bool:
        return outlets[cluster] >= RELABEL_GROWTH * (story.labeled_with or 0)
    todo = [cluster for cluster, story in stories.items()
            if not story.label or grown(cluster, story) or stale(cluster, story)]
    checks = MAX_SPLIT_CHECKS
    for cluster in todo[:MAX_LABELS_PER_RUN]:
        part = df[df['cluster'] == cluster]
        if seen is not None:
            part = part.loc[seen[part.index].sort_values(ascending=False).index]
        story = stories[cluster]
        if SPLIT_DEVELOPMENTS and story.label:  # due a new title: a new development, or the same news?
            since = written(story).to_pydatetime()
            sides = development_sides(story.id, since)
            if min(map(len, sides)) >= SPLIT_LEAST:
                if not checks:
                    continue  # the run's questions are spent: next run, title and all
                checks -= 1
                if (new := split_development(story.id, since, now, sides)) is not None:
                    stories[cluster] = new  # the cluster goes on as the new story, titled from its newest headlines
                    labels.pop(cluster, None)
                    if seen is not None and (seen[part.index] > since).any():
                        part = part[seen[part.index] > since]
        headlines = '\n'.join(f'- {title}' for title in part['title'][:LABEL_FROM])
        result = llm.complete_json(LABEL_PROMPT.format(headlines=headlines), LABEL_SCHEMA, max_tokens=64)
        label = (result or {}).get('title', '').strip().rstrip('.')
        if not label:
            continue
        label = restore_case(label, part['title'])
        with Session() as s, SqlLock:
            story = s.get(Story, stories[cluster].id)
            story.label = label
            story.labeled_with = int(outlets[cluster])
            s.commit()
        labels[cluster] = label
        labeled_at[str(stories[cluster].id)] = now.isoformat(timespec='seconds')
    write_json(LABELED_AT, labeled_at)
    return labels


# A story's title is written while it's on the front pages, from its newest headlines, and stood for good once it
# left: but its headlines can move to another story after (a headline joins the story it clusters with now), so a part
# could keep a title for news it no longer holds. Oct 14, saga 48: "Senators Collins and Jackson debate in Maine",
# written while the cluster held both debates of that night, stood over ten Georgia headlines once the Maine ones had
# gone. So a story that has left the front pages is titled once more, from the headlines it ended with.
FINAL_AFTER = td(hours=2)  # off the front pages this long: it has left (RETURN_GAP is the shorter wait for a return)
FINAL_WITHIN = td(days=7)  # stories that left in this window (sagas show their parts for a week: SAGA_MEMORY)
FINAL_PER_RUN = 25  # about a week's ended stories within a day; saga parts first
FINALS = os.path.join(Config.data, 'story_final_labels.json')  # story id -> {'at', 'from': the title it replaced}


def label_ended(now: dt | None = None, limit: int = FINAL_PER_RUN) -> dict[int, str]:
    """A last title for each story that left the front pages lately and has none written since it left: story id ->
    its new title (written only when it differs)"""
    if llm.backend() is None:
        return {}
    now = now or dt.now(pytz.UTC).replace(tzinfo=None)
    done = read_json(FINALS, {})
    labeled_at = read_json(LABELED_AT, {})
    out = {}
    with Session() as s:
        ended = s.query(Story).filter(Story.last_seen < now - FINAL_AFTER, Story.last_seen >= now - FINAL_WITHIN) \
            .order_by(Story.saga_id.is_(None), Story.last_seen.desc()).all()
        todo = [x for x in ended if str(x.id) not in done][:limit]
        titles = {x.id: [t for (t,) in s.query(Headline.title).join(StoryHeadline, StoryHeadline.headline_id == Headline.id)
                         .filter(StoryHeadline.story_id == x.id).order_by(Headline.first_accessed.desc()).limit(LABEL_FROM)]
                  for x in todo}
        old = {x.id: x.label for x in todo}
    for sid in old:
        if not titles[sid]:
            continue
        result = llm.complete_json(LABEL_PROMPT.format(headlines='\n'.join(f'- {t}' for t in titles[sid])), LABEL_SCHEMA,
                                   max_tokens=64)
        label = (result or {}).get('title', '').strip().rstrip('.')
        if not label:
            continue
        label = restore_case(label, titles[sid])
        done[str(sid)] = {'at': now.isoformat(timespec='seconds'), 'from': old[sid]}
        if label != old[sid]:
            with Session() as s, SqlLock:
                story = s.get(Story, sid)
                if story is not None:
                    story.label = label
                    s.commit()
            labeled_at[str(sid)] = now.isoformat(timespec='seconds')
            out[sid] = label
            logger.info("Story %d titled again as it ended: %s (was: %s)", sid, label, old[sid])
    write_json(FINALS, done)
    write_json(LABELED_AT, labeled_at)
    return out


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
