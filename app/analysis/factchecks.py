"""Fact-checks (#153): which current stories and which folklore narratives the fact-checkers have examined. A rumor
that has been fact-checked is a rumor that got far enough to need it, and the checker's own headline sits beside the
model's reading of what people are saying.

Items come from fact-checkers' own feeds (app/sidefeeds.py, kind 'fact-check'). Each is tied to a story or narrative
(app/analysis/ties.py) only when one is at least SIM_FLOOR alike and the model, offered the closest few and "none",
picks it. Checked by hand on Oct 4 against the day's stories and narratives: ties at 0.59 and up were right (fake
FlyDubai videos, the Cornell rumors, Christa Pike's execution team, Trump's ".si" domain); under 0.58 they were
mostly a different claim on the same subject (FactCheck.org on Trump's taxpayer-funded ads matched Ken Paxton's ads
at 0.56)."""
import json
import os

from app.analysis.ties import tie
from app.utils import Config, get_logger

logger = get_logger(__name__)

STORY_CACHE = os.path.join(Config.data, 'factcheck_story_links.json')
NARRATIVE_CACHE = os.path.join(Config.data, 'factcheck_narrative_links.json')
STORY_DAYS = 7  # a story on the front page now may have been checked last week
NARRATIVE_DAYS = 30  # folklore lives longer than the news
SIM_FLOOR = 0.6
CANDIDATES = 3

PROMPT = """{source} is a fact-checker. Its piece:
{title}
{summary}

Candidates:
{options}

Is this fact-check about one of the candidates? Give its number, or "none" if it's about a different event or \
person and only shares a subject. Fact-checks of fake videos or rumors about an event are about that event."""


def _items(days: int) -> list[dict]:
    from app import sidefeeds
    return sidefeeds.of_kind('fact-check', days)


def for_stories(stories: dict[int, str], items: list[dict] | None = None) -> dict[int, list[dict]]:
    """story id -> fact-checks examining it, newest first. `stories`: id -> its title."""
    items = _items(STORY_DAYS) if items is None else items
    return tie(items, stories, PROMPT, STORY_CACHE, SIM_FLOOR, 'Fact-checks (stories)', CANDIDATES,)


def for_narratives(claims: dict[int, str], items: list[dict] | None = None) -> dict[int, list[dict]]:
    """narrative index -> fact-checks examining its claim. `claims`: index -> the claim in the model's words."""
    items = _items(NARRATIVE_DAYS) if items is None else items
    return tie(items, claims, PROMPT, NARRATIVE_CACHE, SIM_FLOOR, 'Fact-checks (narratives)', CANDIDATES,
               max_new=200)


# Each fact-check read the way the folklore narratives are (app/narratives.py: the same genres, Motif-Index
# chapters and cast), so the rumors fact-checkers take on can be read beside what people retell. No verdicts: the
# feeds' titles are often questions ("Was X...?"), and the model guessed ratings the checkers never gave (Oct 4);
# real ratings would come from the fact-checkers' own ClaimReview data (Google's Fact Check Tools API)
LABELS = os.path.join(Config.data, 'factcheck_labels.json')  # url -> labels, kept for good (a few KB a day)
LABEL_DAYS = 30
MAX_LABELS = 40  # model calls a run, at most
LABEL_PROMPT = """{source}, a fact-checker, published this:
{title}
{summary}

Read it as a folklorist would. Answer in the fields below.

claim: the claim or rumor it checks, in one plain sentence as people state it ("Cornell was dropped from the Ivy \
League"), or "" if it checks no single claim
genre: what kind of story the claim is, one of {genres}
motif_chapter: the chapter of Thompson's Motif-Index the claim fits best, one of {chapters}
motif: the specific motif in a few words of your own, describing this claim, or ""
villain: who the claim casts as the villain, or ""
victim: who the claim casts as the victim, or ""
politics: true if it is about politics or public life"""


def label_schema() -> dict:
    from app.narratives import GENRES, MOTIF_CHAPTERS
    return {"type": "object", "properties": {
        "claim": {"type": "string", "maxLength": 240},
        "genre": {"type": "string", "enum": GENRES}, "motif_chapter": {"type": "string", "enum": MOTIF_CHAPTERS},
        "motif": {"type": "string", "maxLength": 80}, "villain": {"type": "string", "maxLength": 120},
        "victim": {"type": "string", "maxLength": 120}, "politics": {"type": "boolean"}},
        "required": ["claim", "genre", "motif_chapter", "motif", "villain", "victim", "politics"]}


def load_labels() -> dict:
    try:
        with open(LABELS) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def label_all(items: list[dict] | None = None, limit: int = MAX_LABELS) -> dict:
    """Label the fact-checks from the last LABEL_DAYS that have no labels yet (at most `limit` model calls); returns
    every label, url -> labels."""
    from app.analysis import llm
    from app.narratives import GENRES, MOTIF_CHAPTERS
    labels = load_labels()
    items = _items(LABEL_DAYS) if items is None else items
    todo = [i for i in items if i['url'] not in labels][:limit]
    if not todo or llm.backend() is None:
        return labels
    schema = label_schema()
    for item in todo:
        answer = llm.complete_json(LABEL_PROMPT.format(
            source=item['source'], title=item['title'], summary=(item.get('summary') or '')[:400],
            genres='; '.join(GENRES), chapters='; '.join(MOTIF_CHAPTERS)),
            schema, max_tokens=300)
        if answer:
            labels[item['url']] = {**answer, 'model': llm.model()}
    with open(LABELS, 'w') as f:
        json.dump(labels, f)
    logger.info("Fact-checks: labeled %d (%d in all)", len(todo), len(labels))
    return labels
