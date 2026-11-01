"""Import for the showclaims group (see scripts/json_import/__init__.py): the shows' and the Focus Group's claims,
what the shows retold, the shows' published transcripts and the episodes read again into data.db
(app/tables/showclaims.py); the show claims' story ties (worked out from embeddings) move to the cache."""
import os
from datetime import datetime as dt, timedelta as td

from sqlalchemy import insert

from app.utils.store import read_json

TIES = 'show_story_ties.json'


def run(session, data: str, cache: str) -> dict:
    from app.tables import showclaims as t
    counts = {}
    for name, reader in (('show_claims.json', t.SHOWS), ('focus_group_claims.json', t.FOCUS_GROUP)):
        store = read_json(os.path.join(data, name), {})
        t.save_episodes(reader, store, session=session)
        counts[name] = len(store)
    retold = read_json(os.path.join(data, 'show_claims_retold.json'), [])
    t.save_retold(retold, session=session)
    counts['show_claims_retold.json'] = len(retold)

    path = os.path.join(data, 'feed_transcripts.json')
    links = read_json(path, {})
    if links:  # oldest first in the file: seen a second apart, ending when it was last written, keeps that order
        last = dt.fromtimestamp(os.path.getmtime(path)).replace(microsecond=0)
        session.execute(insert(t.FeedTranscript), [
            {'item_url': k, 'transcript_url': v, 'seen': last - td(seconds=len(links) - n)}
            for n, (k, v) in enumerate(links.items(), 1)])
    counts['feed_transcripts.json'] = len(links)

    done = read_json(os.path.join(data, 'retranscribe_claims.json'), {})
    if done:
        session.execute(insert(t.RetranscribedClaims), [
            {'url': url, 'at': dt.fromisoformat(d['at']), 'found': d.get('found', 0), 'added': d.get('added', 0)}
            for url, d in done.items()])
    counts['retranscribe_claims.json'] = len(done)

    counts[TIES] = 0
    if os.path.exists(os.path.join(data, TIES)):
        os.makedirs(cache, exist_ok=True)
        os.replace(os.path.join(data, TIES), os.path.join(cache, TIES))
        counts[TIES] = 1
    return counts
