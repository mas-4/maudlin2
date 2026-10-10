"""Fact-checks (#153): which current stories and which folklore narratives the fact-checkers have examined. A rumor
that has been fact-checked is a rumor that got far enough to need it, and the checker's own headline sits beside the
model's reading of what people are saying.

Items come from fact-checkers' own feeds (app/sidefeeds.py, kind 'fact-check'). Each is tied to a story or narrative
(app/analysis/ties.py) only when one is at least SIM_FLOOR alike and the model, offered the closest few and "none",
picks it. Checked by hand on Oct 4 against the day's stories and narratives: ties at 0.59 and up were right (fake
FlyDubai videos, the Cornell rumors, Christa Pike's execution team, Trump's ".si" domain); under 0.58 they were
mostly a different claim on the same subject (FactCheck.org on Trump's taxpayer-funded ads matched Ken Paxton's ads
at 0.56)."""
import os
from datetime import UTC, datetime as dt, timedelta as td

from app.analysis.ties import tie
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

STORY_CACHE = os.path.join(Config.data, 'factcheck_story_links.json')
NARRATIVE_CACHE = os.path.join(Config.data, 'factcheck_narrative_links.json')
# The story pages' own answers: a week of stories, so a story that left the front page (or never made a card) still
# gets the checks that came after. Its own file, since a tie cache keeps only one run's answers and the front page's
# set of stories differs
PAGE_CACHE = os.path.join(Config.data, 'factcheck_story_page_links.json')
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


def for_story_pages(stories: dict[int, str], items: list[dict] | None = None) -> dict[int, list[dict]]:
    """story id -> fact-checks examining it, for the story pages: every story of the last week, by its label"""
    items = _items(STORY_DAYS) if items is None else items
    return tie(items, stories, PROMPT, PAGE_CACHE, SIM_FLOOR, 'Fact-checks (story pages)', CANDIDATES)


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
# Gemma 4 26B since Oct 10 (Qwen3 8B before): on the person's corrected fact-check claims it wrote closer to their
# wording (W1: 0.791 against 0.746 alike), with fewer verdicts slipped in
LABEL_MODEL = 'gemma4:26b'
LABEL_PROMPT = """{source}, a fact-checker, published this:
{title}
{summary}
{article}
Read it as a folklorist would. Answer in the fields below.

claim: the claim or rumor it checks, the way the people spreading it state it: what they say is true ("the moon \
landing was staged"), never the fact-checker's correction or verdict ("the moon landing photos are genuine"). One or \
two plain sentences, as full as the piece shows it: who says it (a politician, posts on social media, a viral video) \
and in what setting when that's part of the story, and what exactly they say, not the headline's shorthand. "" if it \
checks no single claim.{examples}
context: two or three plain sentences on what the piece shows: who made or spread the claim, where, and what the \
fact-checker found
genre: what kind of story the claim is, one of {genres}
motif_chapter: the chapter of Thompson's Motif-Index the claim fits best, one of {chapters}
motif: the specific motif in a few words of your own, describing this claim, or ""
{shapes}
politics: true if it is about politics or public life"""


def label_schema() -> dict:
    from app.analysis.rumor_shapes import SCHEMA_FIELDS
    from app.narratives import GENRES, MOTIF_CHAPTERS
    return {"type": "object", "properties": {
        "claim": {"type": "string", "maxLength": 360}, "context": {"type": "string", "maxLength": 700},
        "genre": {"type": "string", "enum": GENRES}, "motif_chapter": {"type": "string", "enum": MOTIF_CHAPTERS},
        "motif": {"type": "string", "maxLength": 80}, "politics": {"type": "boolean"},
        **SCHEMA_FIELDS},
        "required": ["claim", "context", *SCHEMA_FIELDS, "genre", "motif_chapter", "motif", "politics"]}


def load_labels() -> dict:
    return read_json(LABELS, {})


ARTICLE_CHARS = 3500  # of the piece's text shown to the model (factcheck_text.py)
EXAMPLES = 5  # of the person's corrections of claims shown as examples


def correction_examples(index: dict | None = None, n: int = EXAMPLES) -> str:
    """The person's latest corrections of claims' wording (motif checker ✎), as examples of what a claim should say:
    who says it and in what setting, not a flattened headline (Oct 8: 46 of them)"""
    from app.analysis import motif_index as mi
    fixes = [(a, b) for a, b in (index if index is not None else mi.load()).get('corrections', {}).items()
             if a != b and len(a) < 300 and len(b) < 300][-n:]
    if not fixes:
        return ''
    return ('\nHow a person corrected claims worded too loosely before (do as they did):\n'
            + '\n'.join(f'- "{a}" became "{b}"' for a, b in fixes))


def waiting_for_text(item: dict, texts: dict) -> bool:
    """A piece whose text may still come (factcheck_text.gather): its label waits a day for it"""
    from app.analysis import factcheck_text as ft
    kept = texts.get(item['url']) or {}
    if kept.get('text') or kept.get('tries', 0) >= ft.MAX_TRIES:
        return False
    try:
        return dt.now(UTC).replace(tzinfo=None) - dt.fromisoformat(str(item.get('published'))[:19]) < td(days=1)
    except ValueError:
        return False


def label_all(items: list[dict] | None = None, limit: int = MAX_LABELS) -> dict:
    """Label the fact-checks from the last LABEL_DAYS that have no labels yet (at most `limit` model calls), from the
    piece's own text when it's been read (factcheck_text.py); returns every label, url -> labels. A piece labeled
    before keeps its claim if that claim is already in the motif index (filed, or corrected by the person): the new
    reading goes in as its context and 'claim from the piece', so nothing the person filed changes under them."""
    from app.analysis import factcheck_text as ft, llm, motif_index as mi
    from app.analysis.rumor_shapes import prompt_fields, settle
    from app.narratives import GENRES, MOTIF_CHAPTERS
    labels = load_labels()
    items = _items(LABEL_DAYS) if items is None else items
    texts = read_json(ft.TEXTS, {})
    fields = set(label_schema()['required'])
    todo = [i for i in items if not fields <= set(labels.get(i['url'], {})) and not waiting_for_text(i, texts)][:limit]
    if not todo or llm.backend() is None:
        return labels
    schema = label_schema()
    index = mi.load()
    examples = correction_examples(index)
    read = {item['url']: ft.text_of(item['url'], texts) for item in todo}

    def ask(item):
        text = read[item['url']]
        return llm.complete_json(LABEL_PROMPT.format(
            source=item['source'], title=item['title'], summary=(item.get('summary') or '')[:400],
            article=f'\nThe piece itself:\n{text[:ARTICLE_CHARS]}\n' if text else '', examples=examples,
            genres='; '.join(GENRES), chapters='; '.join(MOTIF_CHAPTERS), shapes=prompt_fields()),
            schema, max_tokens=700, model=LABEL_MODEL)
    for item, answer in zip(todo, llm.parallel(ask, todo)):  # four at once: the bigger model is slower a call
        text = read[item['url']]
        if answer:
            old = (labels.get(item['url']) or {}).get('claim')
            new = {**settle(answer), 'model': LABEL_MODEL, 'read': 'piece' if text else 'feed'}
            if old and new.get('claim') != old and (mi.key(old) in index.get('claims', {}) or old in index.get('corrections', {})):
                new['claim from the piece'], new['claim'] = new.get('claim'), old
            labels[item['url']] = new
    write_json(LABELS, labels)
    logger.info("Fact-checks: labeled %d (%d in all)", len(todo), len(labels))
    return labels
