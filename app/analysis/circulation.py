"""Whether the rumors fact-checkers examine are circulating among ordinary people (#153): each fact-checked claim
is looked for in our Bluesky and Mastodon sample (app/vernacular.py). Posts at least CANDIDATE alike to the claim (by
meaning) are candidates; up to CHECK of them are read one at a time by the model, which says whether each is telling
the claim, arguing against it (sharing the fact-check counts), only about the news around it, or something else.
Only counts are kept and shown, never posts.

The closest posts are often people sharing the fact-check or the news report itself (Oct 4: the closest post to
FactCheck.org's piece on ads about Susan Collins was its own opening line), which is why stance is asked: telling a
rumor and debunking it are both circulation, but not the same finding."""
import hashlib
import json
import os
from datetime import datetime as dt

import numpy as np

from app.analysis import llm
from app.utils import Config, get_logger

logger = get_logger(__name__)

SEEN = os.path.join(Config.data, 'factcheck_seen.json')  # url -> counts, from the latest nightly look
CACHE = os.path.join(Config.data, 'narratives', 'stance_judgments.json')
HOURS = 72
CANDIDATE = 0.72  # Oct 4: at 0.75, 13 of 94 claims had any post at all in a half-day sample; most single posts
CHECK = 12
STANCES = ['telling it', 'arguing against it', 'about the news, not the claim', 'something else']
PROMPT = """A claim: {claim}

A post: {post}

What does the post do with the claim? "telling it" if it states, repeats or spreads the claim; "arguing against \\
it" if it disputes or debunks it (sharing a fact-check counts); "about the news, not the claim" if it's about the \\
same news but doesn't take up this claim; "something else" if it's about something else."""
SCHEMA = {"type": "object", "properties": {"stance": {"type": "string", "enum": STANCES}}, "required": ["stance"]}


def seen(claims: dict[str, str], hours: float = HOURS) -> dict:
    """url -> {'telling', 'arguing', 'people', 'candidates', 'checked', 'at'} for each claim, from the sample of the
    last `hours`; written to SEEN."""
    from app import narratives
    posts = narratives.load(hours)
    if not posts or not claims or llm.backend() is None:
        return {}
    v = narratives.embed([p['text'] for p in posts])
    urls = list(claims)
    q = narratives.embed([claims[u] for u in urls])
    try:
        with open(CACHE) as f:
            cache = json.load(f)
    except (OSError, ValueError):
        cache = {}
    out = {}
    for url, row in zip(urls, q @ v.T):
        found = np.where(row >= CANDIDATE)[0]
        found = found[np.argsort(-row[found])]
        votes = []
        for i in found[:CHECK]:
            post = posts[int(i)]
            key = hashlib.sha1(f"{PROMPT}\n{claims[url]}\n{post['key']}".encode()).hexdigest()
            if key not in cache:
                answer = llm.complete_json(PROMPT.format(claim=claims[url], post=post['text'][:400]), SCHEMA,
                                           max_tokens=20)
                if not answer:
                    continue
                cache[key] = answer['stance']
            votes.append((cache[key], post['author']))
        telling = {a for s, a in votes if s == 'telling it'}
        arguing = {a for s, a in votes if s == 'arguing against it'}
        out[url] = {'telling': len(telling), 'arguing': len(arguing), 'people': len(telling | arguing),
                    'candidates': int(len(found)), 'checked': len(votes),
                    'at': dt.now().isoformat(timespec='minutes')}
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, 'w') as f:
        json.dump(cache, f)
    with open(SEEN, 'w') as f:
        json.dump({'hours': hours, 'posts': len(posts), 'at': dt.now().isoformat(timespec='minutes'),
                   'claims': out}, f)
    logger.info("Circulation: %d of %d fact-checked claims seen in %d posts (%g hours)",
                sum(1 for c in out.values() if c['people']), len(out), len(posts), hours)
    return out


def load() -> dict:
    try:
        with open(SEEN) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def nightly():
    """Look for every fact-checked claim from the last 30 days."""
    from app.analysis import factchecks
    labels = factchecks.load_labels()
    urls = {i['url'] for i in factchecks._items(factchecks.LABEL_DAYS)}
    seen({u: l['claim'] for u, l in labels.items() if u in urls and l.get('claim')})
