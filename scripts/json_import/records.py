"""Import for the records group (see scripts/json_import/__init__.py): polls.json, bluesky_examples.json,
cloud_history.json, scraper_history.json and newsiness.json into their tables. No caches in this group."""
import os
from datetime import datetime as dt, UTC

from app.utils.store import read_json


def run(session, data: str, cache: str) -> dict:
    from app import bluesky_examples
    from app.analysis import newsiness
    from app.polling import save_polls
    from app.tables.records import BlueskyPost, CloudWord, NewsinessPoint, ScraperRun
    counts = {}

    path = os.path.join(data, 'polls.json')
    polls = read_json(path, [])
    if polls:  # the file's time stands for when it was fetched, so the next run doesn't fetch again at once
        save_polls(session, polls, dt.fromtimestamp(os.path.getmtime(path), UTC).replace(tzinfo=None))
    counts['poll'] = len(polls)

    posts = read_json(os.path.join(data, 'bluesky_examples.json'), {})
    session.bulk_insert_mappings(BlueskyPost, [bluesky_examples.as_row(u, p) for u, p in posts.items()])
    counts['bluesky_post'] = len(posts)

    clouds = read_json(os.path.join(data, 'cloud_history.json'), [])
    words = [{'at': dt.fromisoformat(h['at']), 'rank': i, 'word': w} for h in clouds for i, w in enumerate(h['words'])]
    session.bulk_insert_mappings(CloudWord, words)
    counts['cloud_word'] = len(words)

    history = read_json(os.path.join(data, 'scraper_history.json'), {})
    runs = [{**{k: r.get(k) for k in ('url', 'found', 'kept', 'added', 'too_long', 'error')}, 'agency': agency,
             'at': dt.fromisoformat(r['at'])} for agency, rs in history.items() for r in rs]
    session.bulk_insert_mappings(ScraperRun, runs)
    counts['scraper_run'] = len(runs)

    points = read_json(os.path.join(data, 'newsiness.json'), {})
    rows = [newsiness.as_row(made, p) for made in ('recorded', 'reconstructed') for p in points.get(made, [])]
    session.bulk_insert_mappings(NewsinessPoint, rows)
    counts['newsiness_point'] = len(rows)
    session.flush()
    return counts
