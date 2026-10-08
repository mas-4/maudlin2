"""News or evergreen (Oct 8, the person: "some of these have deep dives on history"): each new episode of the shows we
follow (podcasts, call-ins, video) read from its title and blurb as reacting to the week's news, an evergreen piece
(history, a life story, a long-running topic, self-help, comedy not tied to the news), or a mix. A label, not a filter:
motifs live in history talk too. It orders transcription (the news first, within each tier) and keeps evergreen
episodes out of what counts as retold this week (app/analysis/show_claims.py). Kept in KINDS, url -> kind."""
import os

from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

KINDS = os.path.join(Config.data, 'episode_kinds.json')
SHOW_KINDS = ('podcast', 'call-in', 'video')
BATCH = 10  # episodes read in one call
PER_RUN = 80
DAYS = 3
PROMPT = """Episodes of podcasts, radio call-in shows and political video channels, each its show, title and blurb:
{episodes}

For each, is it reacting to the week's news (current events, the politics of the moment), an evergreen piece not tied \
to this week (history, a life story, a long-running topic, self-help, comedy riffs), or a mix of both?

kinds: one for each episode, in order: "news", "evergreen" or "mixed\""""


def load() -> dict:
    return read_json(KINDS, {})


def evergreen(url: str, kinds: dict | None = None) -> bool:
    return (kinds if kinds is not None else load()).get(url) == 'evergreen'


def label_new(per_run: int = PER_RUN) -> int:
    """Label the shows' episodes of the last DAYS that have no label yet (at most `per_run`); how many"""
    from app import sidefeeds
    from app.analysis import llm
    if llm.backend() is None:
        return 0
    kinds = load()
    names = {s['key']: s['name'] for s in sidefeeds.SOURCES if s['kind'] in SHOW_KINDS}
    todo = [i for i in sidefeeds.items_of(list(names), DAYS) if i['url'] not in kinds][:per_run]
    done = 0
    for start in range(0, len(todo), BATCH):
        part = todo[start:start + BATCH]
        listing = '\n'.join(f'{n}. {names[i["source"]]}: {i["title"]} — {(i.get("summary") or "")[:300]}'
                            for n, i in enumerate(part, 1))
        schema = {"type": "object", "properties": {"kinds": {"type": "array", "minItems": len(part), "maxItems": len(part),
                                                             "items": {"type": "string", "enum": ["news", "evergreen", "mixed"]}}},
                  "required": ["kinds"]}
        answer = llm.complete_json(PROMPT.format(episodes=listing), schema, max_tokens=300)
        if not answer or len(answer.get('kinds', [])) != len(part):
            continue
        for i, k in zip(part, answer['kinds']):
            kinds[i['url']] = k
            done += 1
    write_json(KINDS, kinds)
    if done:
        logger.info("Episodes: %d labeled news or evergreen", done)
    return done
