"""Which of today's stories the satire sites are joking about (#139). Satire is fiction that answers the news the same
day, and it splits by side (the Babylon Bee on the right; the Onion, Borowitz and McSweeney's on the left), so which
stories become jokes, and on which side, is a reading of the news in itself.

Each joke from the last DAYS is tied to the story it's about, if any (app/analysis/ties.py): the closest CANDIDATES
stories at least SIM_FLOOR alike, then the model's forced choice among them with "none" on offer.

Jokes are only ever shown as jokes, labeled 🃏 on the story they're about: never counted as coverage, never in the
cloud, the stories' outlets or any measure."""
import os

from app.analysis.ties import tie
from app.utils import Config
from app.utils.store import read_json

CACHE = os.path.join(Config.data, 'satire_links.json')
DAYS = 3
CANDIDATES = 3
# Only stories at least this close in meaning (mxbai-embed-large) are offered. Checked by hand on Oct 4: every wrong
# match the model made was under 0.48 ("Woman survives two minutes in Primark" -> a botched execution, a
# paste-eating Marine -> a Marine arrested in Japan); three of four right ones were over 0.54
SIM_FLOOR = 0.5
MAX_NEW = 40  # model calls a run, at most

PROMPT = """{source} is a satire site: this headline is a joke, not real news.
Joke: {title}
{summary}

Today's real news stories:
{options}

Which story is the joke about? Pick a number only if the joke plainly makes fun of that same news event, or the \
same people in that news. A joke about a general subject (politics, work, dating, the economy) that isn't tied to \
one of these stories is "none". Answer with the story's number, or none."""


def _load() -> dict:
    return read_json(CACHE, {})


def jokes(stories: dict[int, str], items: list[dict] | None = None) -> dict[int, list[dict]]:
    """story id -> the satire pieces joking about it, newest first. `stories`: id -> its title."""
    if items is None:
        from app import sidefeeds
        items = sidefeeds.satire(DAYS)
    return tie(items, stories, PROMPT, CACHE, SIM_FLOOR, 'Satire', CANDIDATES, MAX_NEW)
