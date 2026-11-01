"""Import for the runstate group (see scripts/json_import/__init__.py): the small singletons into run_state, each
under its file's name without .json and dated by the file's time; factcheck_seen's claims, the motif index's daily
metrics and the model scout's seen models into rows; the outlet profile, the Replay and the momentum tables, all
rebuilt from the database when missing, moved into the cache folder; the archive's days (archive/days.json) into
archive_day rows (the dated editions stay files). outlet_profile.before-credit-delete.json and
epithet_candidates.json are read by nothing and left where they are."""
import json
import os
from datetime import datetime as dt, UTC

from app.utils.store import read_json

SINGLETONS = ['health', 'newsday', 'worker', 'gpu_lease', 'sidefeeds_state', 'chyrons/state', 'scotus_docket',
              'outlet_wiki', 'investigations', 'aggregates', 'motif_proposals_runs', 'validation/today',
              'gaming', 'lights_party', 'deck_seen', 'retranscribe_failed']
CACHES = ['outlet_profile.json', 'replay.json', 'momentum.json']
SEEN_FIELDS = ('telling', 'arguing', 'people', 'candidates', 'checked')


def _at(path: str) -> dt:
    return dt.fromtimestamp(os.path.getmtime(path), UTC).replace(tzinfo=None)


def run(session, data: str, cache: str) -> dict:
    from app.tables.runstate import ArchiveDay, FactcheckSeen, ModelSeen, MotifMetricsDay, RunState
    states = []
    for name in SINGLETONS:
        path = os.path.join(data, name + '.json')
        value = read_json(path, None)
        if value is not None:
            states.append({'name': name, 'value': json.dumps(value), 'at': _at(path)})

    seen_path = os.path.join(data, 'factcheck_seen.json')
    look = read_json(seen_path, {})
    claims = look.pop('claims', None) or {}
    if look:
        states.append({'name': 'factcheck_seen', 'value': json.dumps(look), 'at': _at(seen_path)})
    seen = [{'url': url, **{f: int(c.get(f) or 0) for f in SEEN_FIELDS}, 'at': c.get('at') or look.get('at') or ''}
            for url, c in claims.items() if isinstance(c, dict)]

    metrics = read_json(os.path.join(data, 'motifs', 'metrics.json'), {})
    days = [{'day': day, 'shape': json.dumps(shape)} for day, shape in metrics.items() if isinstance(shape, dict)]

    scout = (read_json(os.path.join(data, 'model_scout.json'), {}) or {}).get('seen') or {}
    models = [{'key': k, 'first_seen': day} for k, day in scout.items()]

    archive = read_json(os.path.join(data, 'archive', 'days.json'), {}) or {}
    editions = [{'day': day, 'label': d.get('label'), 'emoji': d.get('emoji'), 'story': d.get('story'),
                 'stories': d.get('stories')} for day, d in archive.items() if isinstance(d, dict)]

    for model, rows in ((RunState, states), (FactcheckSeen, seen), (MotifMetricsDay, days), (ModelSeen, models),
                        (ArchiveDay, editions)):
        if rows:
            session.bulk_insert_mappings(model, rows)

    moved = 0
    for name in CACHES:
        src, dst = os.path.join(data, name), os.path.join(cache, name)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            moved += 1
    return {'run_state': len(states), 'factcheck_seen': len(seen), 'motif_metrics_day': len(days),
            'model_seen': len(models), 'archive_day': len(editions), 'caches moved': moved}
