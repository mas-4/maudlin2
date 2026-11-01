"""Import for the motifs group (see scripts/json_import/__init__.py): the proposals, the checker's undo stack, the watch
list and the reranker's teaching into their tables; the motif signals' model answers moved into the cache folder.
validation/motifs/ (the Oct 4 model comparison) is read by nothing and left where it is."""
import glob
import json
import os

from app.utils.store import read_json

PROPOSAL_FIELDS = ('id', 'kind', 'status', 'args', 'reason', 'model', 'made', 'decided', 'why', 'final', 'judge', 'fit')
PROPOSAL_JSON = ('args', 'final', 'judge')
WATCH_FIELDS = ('claim', 'source', 'ref', 'date', 'story', 'story_tie', 'plain', 'why', 'since', 'refiled')
TEACHING_FIELDS = ('at', 'examples', 'decisions', 'taught_auc', 'base_auc', 'kept')
# Model answers, rebuilt if lost: moved to the cache folder under the same relative names
CACHES = ['motifs/claim_shapes.json', 'motifs/claim_layers.json', 'motifs/motif_elements.json',
          'motifs/filing_alternatives.json', 'motifs/glean.json', 'motifs/motif_space.json',
          'motifs/reranker/held_out.json']


def proposal_row(p: dict) -> dict:
    row = {f: (json.dumps(p[f]) if f in PROPOSAL_JSON else p[f]) if p.get(f) is not None else None
           for f in PROPOSAL_FIELDS}
    return {**row, 'args': row['args'] or '{}', **{f: row[f] or '' for f in ('reason', 'model', 'made')}}


def undo_rows(folder: str) -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(folder, '*.json'))):  # named by time: oldest first, as ids will be
        snap = read_json(path, None)
        if not isinstance(snap, dict) or not snap.get('path'):
            continue
        out.append({'at': snap.get('at') or os.path.basename(path)[:-5], 'path': snap['path'],
                    'before': snap.get('before'), 'after_sha': snap.get('after_sha') or '', 'after': snap.get('after'),
                    'what': snap.get('what') or '',
                    'proposals': json.dumps(snap['proposals']) if snap.get('proposals') else None,
                    'log': snap.get('log') or None})
    return out


def run(session, data: str, cache: str) -> dict:
    from app.tables.motifs import CheckerUndo, MotifProposal, RerankerTeaching, WatchClaim, WatchUnfound
    counts = {}

    proposals = read_json(os.path.join(data, 'motif_proposals.json'), {})
    session.bulk_insert_mappings(MotifProposal, [proposal_row({**p, 'id': i}) for i, p in proposals.items()])
    counts['motif_proposal'] = len(proposals)

    undo = undo_rows(os.path.join(data, 'validation', 'undo'))
    session.bulk_insert_mappings(CheckerUndo, undo)
    counts['checker_undo'] = len(undo)

    watch = read_json(os.path.join(data, 'motifs', 'watch_list.json'), {})
    claims = watch.get('claims') or {}
    session.bulk_insert_mappings(WatchClaim, [{'key': k, **{f: w.get(f) for f in WATCH_FIELDS},
                                               'plain': bool(w.get('plain'))} for k, w in claims.items()])
    unfound = watch.get('unfound') or {}
    session.bulk_insert_mappings(WatchUnfound, [{'key': k, 'day': d} for k, d in unfound.items()])
    counts['watch_claim'], counts['watch_unfound'] = len(claims), len(unfound)

    taught = read_json(os.path.join(data, 'motifs', 'reranker', 'taught.json'), {})
    if taught.get('at'):
        session.add(RerankerTeaching(**{f: taught.get(f) for f in TEACHING_FIELDS}))
    counts['reranker_teaching'] = int(bool(taught.get('at')))
    session.flush()

    moved = 0
    for rel in CACHES:
        src, dst = os.path.join(data, rel), os.path.join(cache, rel)
        if os.path.exists(src):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(src, dst)
            moved += 1
    counts['caches moved'] = moved
    return counts
