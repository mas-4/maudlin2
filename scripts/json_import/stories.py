"""Import for the stories group (see scripts/json_import/__init__.py): story_merges, story_splits, story_labeled_at,
story_final_labels, sagas_ended, saga_pairs, story_extras and entity_aliases into their tables (app/tables/stories.py);
story_entities and the tie caches (satire_links, factcheck_*_links) move to the cache folder. never_named.json is
kept by hand beside always_named.json: configuration, left where it is."""
import json
import os
from datetime import datetime as dt, UTC

from app.utils.store import read_json

CACHES = ['story_entities.json', 'satire_links.json', 'factcheck_story_links.json', 'factcheck_narrative_links.json',
          'factcheck_story_page_links.json']
EXTRA_KINDS = ['shows', 'factchecks', 'investigations', 'satire', 'curators', 'quotes']


def when(text) -> dt | None:
    """An ISO time from a file as naive UTC (some were written with +00:00, most naive UTC already)"""
    if not text:
        return None
    t = dt.fromisoformat(text)
    return t.astimezone(UTC).replace(tzinfo=None) if t.tzinfo else t


def run(session, data: str, cache: str) -> dict:
    from app.tables.stories import (EntityAlias, EntityNotSame, SagaEnded, SagaPair, StoryExtra, StoryExtraItem,
                                    StoryFinalLabel, StoryLabeledAt, StoryMerge, StorySplit)
    counts = {}

    def put(model, rows):
        session.bulk_insert_mappings(model, rows)
        counts[model.__tablename__] = len(rows)

    merges = read_json(os.path.join(data, 'story_merges.json'), {})
    put(StoryMerge, [{'gone': int(k), 'into': int(v['into']), 'label': v.get('label'),
                      'first_seen': when(v.get('first_seen')), 'headlines': json.dumps(v.get('headlines') or []),
                      'at': when(v.get('at')) or dt(2026, 10, 1), 'why': v.get('why') or ''} for k, v in merges.items()])
    splits = read_json(os.path.join(data, 'story_splits.json'), {})
    put(StorySplit, [{'story_id': int(k), 'into': int(v['into']), 'label': v.get('label'), 'since': when(v['since']),
                      'headlines': json.dumps(v.get('headlines') or []), 'at': when(v['at'])} for k, v in splits.items()])
    labeled = read_json(os.path.join(data, 'story_labeled_at.json'), {})
    put(StoryLabeledAt, [{'story_id': int(k), 'at': when(v)} for k, v in labeled.items() if v])
    finals = read_json(os.path.join(data, 'story_final_labels.json'), {})
    put(StoryFinalLabel, [{'story_id': int(k), 'at': when(v.get('at')) or dt(2026, 10, 1), 'replaced': v.get('from')}
                          for k, v in finals.items()])
    ended = read_json(os.path.join(data, 'sagas_ended.json'), {})
    put(SagaEnded, [{'saga_id': int(k), 'to_saga': v.get('saga'), 'to_story': v.get('story')} for k, v in ended.items()])
    pairs = read_json(os.path.join(data, 'saga_pairs.json'), {})
    rows = {}
    for k, v in pairs.items():
        a, b = sorted(int(x) for x in k.split('|'))
        rows[a, b] = {'story_a': a, 'story_b': b, 'same': bool(v.get('same')), 'judge': v.get('judge'),
                      'hand': bool(v.get('hand')), 'model': v.get('model'), 'at': when(v.get('at')),
                      'titles_a': json.dumps(v.get('a') or []), 'titles_b': json.dumps(v.get('b') or [])}
    put(SagaPair, list(rows.values()))

    extras = read_json(os.path.join(data, 'story_extras.json'), {})
    stories, items = [], {}
    for sid, e in extras.items():
        updated = when(e.get('updated')) or dt(2026, 10, 1)
        stories.append({'story_id': int(sid), 'wording': json.dumps(e.get('wording') or {}), 'updated': updated})
        for kind in EXTRA_KINDS:
            for i, p in enumerate(e.get(kind) or []):
                key = (p.get('phrase') if kind == 'quotes' else p.get('url') or p.get('source')) or ''
                # Every item kept its place in the list, so the story's update time and its place keep the order
                items.setdefault((int(sid), kind, key), {
                    'story_id': int(sid), 'kind': kind, 'key': key, 'source': p.get('source'), 'title': p.get('title'),
                    'url': p.get('url'), 'color': p.get('color'), 'emoji': p.get('emoji'), 'count': p.get('count'),
                    'seen': when(p.get('seen')) or updated, 'ord': i})
    put(StoryExtra, stories)
    put(StoryExtraItem, list(items.values()))

    book = read_json(os.path.join(data, 'entity_aliases.json'), {})
    put(EntityAlias, [{'name': k, 'target': v} for k, v in (book.get('aliases') or {}).items()])
    apart = {tuple(sorted(p)) for p in book.get('not_same') or [] if len(p) == 2}
    put(EntityNotSame, [{'a': a, 'b': b} for a, b in sorted(apart)])
    session.flush()

    moved = 0
    os.makedirs(cache, exist_ok=True)
    for name in CACHES:
        if os.path.exists(os.path.join(data, name)) and not os.path.exists(os.path.join(cache, name)):
            os.replace(os.path.join(data, name), os.path.join(cache, name))
            moved += 1
    counts['caches_moved'] = moved
    return counts
