"""Which of today's stories the satire sites are joking about (#139). Satire is fiction that answers the news the same
day, and it splits by side (the Babylon Bee on the right; the Onion, Borowitz and McSweeney's on the left), so which
stories become jokes, and on which side, is a reading of the news in itself.

Each joke from the last DAYS is compared to the current stories by meaning, and the model picks which of the closest
CANDIDATES (if at least SIM_FLOOR alike) it's about, with "none" on offer (a forced choice: asked yes or no about one story, a small model says yes
to nearly anything). Answers are cached, so each joke is asked about once per set of candidates.

Jokes are only ever shown as jokes, labeled 🃏 on the story they're about: never counted as coverage, never in the
cloud, the stories' outlets or any measure."""
import hashlib
import json
import os
from collections import defaultdict

import numpy as np

from app.analysis import llm
from app.utils import Config, get_logger

logger = get_logger(__name__)

CACHE = os.path.join(Config.data, 'satire_links.json')
DAYS = 3
CANDIDATES = 3
# Only stories at least this close in meaning (mxbai-embed-large) are offered. Checked by hand on Oct 4: every wrong
# match the model made was under 0.48 ("Woman survives two minutes in Primark" -> a botched execution, a
# paste-eating Marine -> a Marine arrested in Japan); three of four right ones were over 0.54
SIM_FLOOR = 0.5
MAX_NEW = 40  # model calls a run, at most

PROMPT = """{outlet} is a satire site: this headline is a joke, not real news.
Joke: {title}
{summary}

Today's real news stories:
{options}

Which story is the joke about? Pick a number only if the joke plainly makes fun of that same news event, or the \
same people in that news. A joke about a general subject (politics, work, dating, the economy) that isn't tied to \
one of these stories is "none"."""


def _load() -> dict:
    try:
        with open(CACHE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def jokes(stories: dict[int, str], items: list[dict] | None = None) -> dict[int, list[dict]]:
    """story id -> the satire pieces joking about it, newest first. `stories`: id -> its title."""
    from app.analysis.clustering import story_similarity
    if items is None:
        from app import sidefeeds
        items = sidefeeds.satire(DAYS)
    if not items or not stories or llm.backend() is None:
        return {}
    ids = list(stories)
    titles = [stories[i] for i in ids]
    similarity, _, model = story_similarity([i['title'] for i in items] + titles)
    if model != 'mxbai-embed-large':  # the floor is for that model's scale: no guessing on another's
        logger.warning("Satire: skipped, story embeddings came from %s", model)
        return {}
    similarity = similarity[:len(items), len(items):]
    cache, used, asked = _load(), {}, 0
    found = defaultdict(list)
    for item, row in zip(items, similarity):
        top = [int(j) for j in np.argsort(-row)[:CANDIDATES] if row[j] >= SIM_FLOOR]
        if not top:
            continue
        options = '\n'.join(f'{n}. {titles[j]}' for n, j in enumerate(top, 1))
        key = hashlib.sha1(f"{PROMPT}\n{item['title']}\n{options}".encode()).hexdigest()[:16]
        if key not in cache:
            if asked >= MAX_NEW:
                continue
            asked += 1
            schema = {"type": "object", "properties": {
                "reason": {"type": "string", "maxLength": 200},
                "story": {"type": "string", "enum": [str(n) for n in range(1, len(top) + 1)] + ['none']}},
                "required": ["reason", "story"]}
            answer = llm.complete_json(PROMPT.format(outlet=item['source'], title=item['title'],
                                                     summary=item['summary'][:300], options=options), schema,
                                       max_tokens=160)
            if not answer:
                continue
            cache[key] = answer.get('story', 'none')
        used[key] = cache[key]
        if used[key] != 'none':
            found[ids[top[int(used[key]) - 1]]].append(item)
    with open(CACHE, 'w') as f:
        json.dump(used, f)  # only this run's answers: the cache never outgrows a run
    logger.info("Satire: %d of %d jokes tied to %d stories (%d new model calls)",
                sum(len(v) for v in found.values()), len(items), len(found), asked)
    return dict(found)
