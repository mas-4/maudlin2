"""Stories are clusters that persist across runs. Matching each run's clusters back to the stories they
continue lets us label a story once, and compare how each outlet covers the same event: an outlet whose
headlines run more negative than everyone else's on the same stories is framing, not just reporting bad news."""
import re
from collections import Counter
from datetime import datetime as dt, timedelta as td

import pandas as pd
import pytz
from sqlalchemy import func, update

from app.analysis import llm
from app.models import Session, SqlLock, Story, StoryHeadline, Headline, Article, Agency
from app.utils import get_logger

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


def sync_stories(df: pd.DataFrame) -> dict[int, Story]:
    """Map each cluster in `df` (one headline per outlet, with a `cluster` and `headline_id` column) to a
    persisted story, recording every headline's deviation from its story's mean sentiment."""
    now = dt.now(pytz.UTC).replace(tzinfo=None)
    stories = {}
    with Session() as s, SqlLock:
        for cluster, group in df.groupby('cluster'):
            ids = [int(i) for i in group['headline_id']]
            # The story that already holds most of these headlines is the one this cluster continues
            match = s.query(StoryHeadline.story_id, func.count().label('n')).filter(
                StoryHeadline.headline_id.in_(ids)
            ).group_by(StoryHeadline.story_id).order_by(func.count().desc()).first()
            if match:
                story = s.get(Story, match.story_id)
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
