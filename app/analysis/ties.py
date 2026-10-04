"""Tie side items (satire jokes, fact-checks) to the stories or narratives they're about: the closest targets by
meaning (mxbai-embed-large, at least `floor` alike, up to `candidates`), then the model's forced choice among them with
"none" on offer. Asked yes or no about one target, a small model says yes to nearly anything; offered a few and
"none", it says none when none fits. Answers are cached for a run, so each item is asked once per set of options."""
import hashlib
import json
from collections import defaultdict

import numpy as np

from app.analysis import llm
from app.utils import get_logger

logger = get_logger(__name__)

EMBEDDINGS = 'mxbai-embed-large'  # the floors are calibrated on this model's scale


def tie(items: list[dict], targets: dict, prompt: str, cache_path: str, floor: float, name: str,
        candidates: int = 3, max_new: int = 40) -> dict:
    """target id -> the items tied to it. `targets`: id -> its text. `prompt` is formatted with the item's source,
    title and summary and the numbered options."""
    from app.analysis.clustering import story_similarity
    if not items or not targets or llm.backend() is None:
        return {}
    ids = list(targets)
    texts = [targets[i] for i in ids]
    similarity, _, model = story_similarity([i['title'] for i in items] + texts)
    if model != EMBEDDINGS:  # no guessing on another model's scale
        logger.warning("%s: skipped, embeddings came from %s", name, model)
        return {}
    similarity = similarity[:len(items), len(items):]
    try:
        with open(cache_path) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    used, asked, found = {}, 0, defaultdict(list)
    for item, row in zip(items, similarity):
        top = [int(j) for j in np.argsort(-row)[:candidates] if row[j] >= floor]
        if not top:
            continue
        options = '\n'.join(f'{n}. {texts[j]}' for n, j in enumerate(top, 1))
        key = hashlib.sha1(f"{prompt}\n{item['title']}\n{options}".encode()).hexdigest()[:16]
        if key not in cache:
            if asked >= max_new:
                continue
            asked += 1
            schema = {"type": "object", "properties": {
                "reason": {"type": "string", "maxLength": 300},  # cut shorter, it can end before the pick
                "pick": {"type": "string", "enum": [str(n) for n in range(1, len(top) + 1)] + ['none']}},
                "required": ["reason", "pick"]}
            answer = llm.complete_json(prompt.format(source=item['source'], title=item['title'],
                                                     summary=(item.get('summary') or '')[:300], options=options),
                                       schema, max_tokens=200)
            if not answer:
                continue
            cache[key] = answer.get('pick', 'none')
        used[key] = cache[key]
        if used[key] != 'none':
            found[ids[top[int(used[key]) - 1]]].append(item)
    with open(cache_path, 'w') as f:
        json.dump(used, f)  # only this run's answers: the cache never outgrows a run
    logger.info("%s: %d of %d items tied to %d targets (%d new model calls)",
                name, sum(len(v) for v in found.values()), len(items), len(found), asked)
    return dict(found)
