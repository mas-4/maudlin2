"""Import for the caches group (see scripts/json_import/__init__.py): the model answers' files move into the cache
folder under the same relative names; the fact-checks' labels, which aren't a cache, go into factcheck_label."""
import os

from app.utils.store import read_json

# Relative to the data folder, and to the cache folder after the move
CACHES = ['edit_judgments.json', 'saga_judgments.json', 'scotus_judgments.json', 'episode_kinds.json',
          'accusations.json', 'subject_tags.json', 'factcheck_texts.json', 'running_order.json', 'story_returns.json',
          'story_seams.json', 'scotus_glosses.json', 'scotus_story_glosses.json', 'narratives/judgments.json',
          'narratives/stance_judgments.json', 'chyrons/clean.json', 'chyrons/matches.json',
          'motifs/pair_judge_cache.json', 'motifs/rerank_cache.json']


def run(session, data: str, cache: str) -> dict:
    from app.tables.caches import FactcheckLabel
    labels = read_json(os.path.join(data, 'factcheck_labels.json'), {})
    rows = [FactcheckLabel.from_dict(url, label) for url, label in labels.items() if isinstance(label, dict)]
    if rows:
        session.bulk_insert_mappings(FactcheckLabel, rows)
    moved = 0
    for name in CACHES:
        src, dst = os.path.join(data, name), os.path.join(cache, name)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            moved += 1
    return {'factcheck_label': len(rows), 'caches moved': moved}
