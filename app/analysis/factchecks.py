"""Fact-checks (#153): which current stories and which folklore narratives the fact-checkers have examined. A rumor
that has been fact-checked is a rumor that got far enough to need it, and the checker's verdict sits beside the
model's reading of what people are saying.

Items come from fact-checkers' own feeds (app/sidefeeds.py, kind 'fact-check'). Each is tied to a story or narrative
(app/analysis/ties.py) only when one is at least SIM_FLOOR alike and the model, offered the closest few and "none",
picks it. Checked by hand on Oct 4 against the day's stories and narratives: ties at 0.59 and up were right (fake
FlyDubai videos, the Cornell rumors, Christa Pike's execution team, Trump's ".si" domain); under 0.58 they were
mostly a different claim on the same subject (FactCheck.org on Trump's taxpayer-funded ads matched Ken Paxton's ads
at 0.56)."""
import os

from app.analysis.ties import tie
from app.utils import Config

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
