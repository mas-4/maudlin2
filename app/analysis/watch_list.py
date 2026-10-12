"""The watch list (Oct 12, the person's decision on Straight news): a claim judged plain news is not terminal. Straight
news stays as a motif, but as a sink and a watch list, not a Perennial. Claims in it, and claims with no motif (a
person's "tells no story", or the filing model's none), are watched and filed again when something changes: weekly
against the index as it has grown, and at once when a narrative thread ties the telling to a later day (the same
narrative told again, app/analysis/narrative_threads.py). A show retelling it isn't caught yet: that needs the claims
compared by meaning, which waits for the weekly pass.

Filing again runs filing's own shortlist and judge (motif_index.Shortlister, name_claim), but file_claims skips any
claim already in the index, so this is its own path. Each pass is logged, dated (REFILE_LOG): the claim, the day it was
reported (t0), and the motifs the judge picked at t (t1), so "a report at t0, told as motif X at t1" is on record. A
pick of a real motif (not Straight news, not one a person took the claim out of) becomes an unchecked filing, marked
'refiled' with what the claim was, which reaches the person's claims to judge like any other; a no there takes it out
again, and a claim left with no motif is back where the person put it. A new name the judge offers is logged, never
made into a motif. Straight news's own pick means it's still plain.

    watch_list.json    {'claims': claim key -> {claim, source, ref, date (t0), story, why ('no motif', 'straight
                       news'), plain (watched now), since, refiled (last pass)}, 'unfound': keys whose words weren't
                       found, with the day they were looked for}
    refile_log.jsonl   one line a pass over a claim"""
import json
import os
from collections import Counter
from datetime import datetime as dt
from datetime import timedelta as td

from app.analysis import llm
from app.analysis import motif_index as mi
from app.utils import Config, get_logger
from app.utils.store import read_json, write_json

logger = get_logger(__name__)

STORE = os.path.join(Config.data, 'motifs', 'watch_list.json')
REFILE_LOG = os.path.join(Config.data, 'motifs', 'refile_log.jsonl')
EVERY = td(days=7)  # a watched claim is filed again at least this often
MAX = 60  # claims a pass, at most (about 2.5 s each with Gemma 4 26B)
BUDGET = 300  # seconds a pass, at most


def load() -> dict:
    return read_json(STORE, {'claims': {}})


def save(store: dict):
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    write_json(STORE, store, indent=1)


def state(index: dict, k: str, plain: str | None) -> str | None:
    """'no motif', 'straight news', or None: the claim tells something now (or has left the index)"""
    if k not in index['claims']:
        return None
    ids = {mi.resolve(index, i) for i in mi._ids(index, k)}
    if not ids:
        return 'no motif'
    return 'straight news' if plain and ids == {plain} else None


def known_texts(index: dict) -> dict[str, dict]:
    """Claim key (as worded now) -> what we know of a claim: its words, source, ref, the day it was reported and its
    story, from wherever its words are kept: the narrative reports, the fact-checks' labels, the Focus Group's and the
    shows' claims, the shortlist log and the curation log. A claim with no motif keeps only its key in the index"""
    import glob

    from app import narratives, sidefeeds
    from app.analysis import curation_db, factchecks, focus_group, show_claims
    out = {}

    def add(text: str, **fields):
        if text:
            text = mi.corrected(text, index)
            out.setdefault(mi.key(text), {'claim': text, **{f: v for f, v in fields.items() if v is not None}})
    for path in sorted(glob.glob(os.path.join(narratives.FOLDER, 'report-*.json')), reverse=True):  # the latest first
        report = read_json(path, {})
        for g in report.get('found', []):
            lab = g.get('label') or {}
            add(lab.get('narrative'), source='narrative', ref=report.get('made', ''),
                date=(report.get('made') or '')[:10], **mi.story_of_group(g))
    labels, checked = factchecks.load_labels(), factchecks.stories_of()
    try:
        items = sidefeeds.of_kind('fact-check', days=3650)
    except Exception as e:  # noqa: BLE001 - the other sources still count
        logger.warning("Watch list: fact-checks unread (%s)", e)
        items = []
    for it in items:
        add((labels.get(it['url']) or {}).get('claim'), source=it['source'], ref=it['url'], date=it['published'][:10],
            story=checked.get(it['url']))
    for c in focus_group.claims():
        add(c['claim'], source=c['source'], ref=c['ref'], date=c.get('date'))
    for r in read_json(show_claims.RETOLD, []):  # as last kept: retold() itself compares claims by meaning
        add(r.get('claim'), source=show_claims.SOURCE, ref=r.get('ref', ''), date=r.get('date'))
    try:
        with open(mi.SHORTLIST_LOG) as f:
            for line in f:
                r = json.loads(line)
                add(r.get('claim'), source=r.get('source', ''), date=r.get('at', '')[:10])
    except (OSError, ValueError):
        pass
    for a in curation_db.actions():
        for s in (a['action'] or {}).get('steps', [a['action'] or {}]):
            if isinstance(s.get('claim'), str):
                add(s['claim'], date=a['at'][:10])
    return out


def sync(index: dict | None = None, store: dict | None = None) -> dict:
    """The watch list brought up to date with the index: Straight news's claims and the claims with no motif in, each
    marked plain or not (a claim that tells something now stays listed, unwatched, with what it was)"""
    index = index if index is not None else mi.load()
    store = store if store is not None else load()
    claims = store.setdefault('claims', {})
    plain = mi.plain_news(index)
    today = dt.now().strftime('%Y-%m-%d')
    for c in (index['entries'].get(plain) or {}).get('claims', []) if plain else []:
        k = mi.key(c['claim'])
        w = claims.setdefault(k, {'key': k, 'since': today})
        w.update({f: c[f] for f in ('claim', 'source', 'ref', 'date', *mi.STORY_FIELDS) if c.get(f) is not None})
    missing = [k for k, ids in index['claims'].items() if not ids and not (claims.get(k) or {}).get('claim')]
    if any(store.get('unfound', {}).get(k) != today for k in missing):  # looked for once a day
        texts = known_texts(index)
        for k in missing:
            if k in texts:
                claims.setdefault(k, {'key': k, 'since': today}).update(texts[k])
        store['unfound'] = {k: today for k in missing if k not in texts}
    for k, w in claims.items():
        why = state(index, k, plain)
        w['plain'] = why is not None
        w['why'] = why or w.get('why')
    unread = sum(1 for k, ids in index['claims'].items() if not ids and k not in claims)
    if unread:
        logger.info("Watch list: %d claims with no motif whose words weren't found", unread)
    return store


def threads_told_again(index: dict) -> dict[str, str]:
    """Claim key (as worded now) -> the latest day its narrative thread told it again, after the day it was told"""
    from app.analysis import narrative_threads
    out = {}
    for t in narrative_threads.load()['threads'].values():
        days = t.get('days') or []
        last = max((d['date'] for d in days), default='')
        for d in days:
            if d['date'] < last:
                k = mi.key(mi.corrected(d['claim'], index))
                out[k] = max(out.get(k, ''), last)
    return out


def due(store: dict, index: dict, now: dt | None = None) -> list[tuple[dict, str]]:
    """The watched claims to file again, with why: told again in a later day's narrative since the last pass, or a
    week since it (never filed again first, then the longest waiting)"""
    now = now or dt.now()
    try:
        again = threads_told_again(index)
    except Exception as e:  # noqa: BLE001 - the weekly pass still runs
        logger.warning("Watch list: narrative threads unread (%s)", e)
        again = {}
    out = []
    for w in store['claims'].values():
        if not w.get('plain') or not w.get('claim'):
            continue
        last = w.get('refiled') or ''
        if again.get(w['key'], '') > max(last[:10], w.get('date') or ''):
            out.append((w, f"told again on {again[w['key']]}"))
        elif not last or dt.fromisoformat(last) <= now - EVERY:
            out.append((w, 'weekly'))
    return sorted(out, key=lambda x: (x[1] == 'weekly', x[0].get('refiled') or ''))


def refile(budget: float | None = BUDGET, limit: int = MAX) -> dict:
    """File the watched claims that are due again against the index as it is now; how many were filed again, by
    outcome ('told': a real motif picked and filed unchecked; 'still plain': Straight news picked; 'new name': only a
    name for a motif we don't have; 'none')"""
    import time
    if llm.backend() is None:
        return {}
    started = time.time()
    index = mi.load()
    store = sync(index)
    todo = due(store, index)[:limit]
    if not todo:
        save(store)
        return {}
    lister = mi.Shortlister(index, [w['claim'] for w, _ in todo], budget=None if budget is None else budget / 2)
    outcomes = Counter()
    for w, why in todo:
        if budget is not None and time.time() - started > budget:
            break  # the rest wait for the next pass
        with mi.locked():
            index = mi.load()
            k, plain = w['key'], mi.plain_news(index)
            was = state(index, k, plain)
            if was is None:  # filed meanwhile
                w['plain'] = False
                continue
            shown = lister(index, w['claim'])
            named = mi.name_claim(w['claim'], shown)
            if not named:
                continue
            at = dt.now().isoformat(timespec='seconds')
            picked = [e['id'] for e in named['existing']]
            filed = []
            for eid in picked:
                entry = index['entries'].get(eid)
                if eid == plain or entry is None or entry.get('merged_into') or k in entry.get('not_claims', []) \
                        or any(mi.key(c['claim']) == k for c in entry['claims']):
                    continue
                rec = mi.record(w, at[:10])
                rec['refiled'] = {'at': at[:10], 'was': was}
                entry['claims'].append(rec)
                entry['last_seen'] = max(entry.get('last_seen', ''), rec['date'])
                filed.append(eid)
            if filed:
                index['claims'][k] = list(dict.fromkeys(mi._ids(index, k) + filed))
                mi.save(index)
        outcome = 'told' if filed else 'still plain' if plain in picked else 'new name' if named['new'] else 'none'
        outcomes[outcome] += 1
        w['refiled'] = at
        os.makedirs(os.path.dirname(REFILE_LOG), exist_ok=True)
        with open(REFILE_LOG, 'a') as f:
            f.write(json.dumps({'at': at, 'key': k, 'claim': w['claim'], 'was': was, 'reported': w.get('date'),
                                'story': w.get('story'), 'why': why, 'shown': [e['id'] for e in shown],
                                'picked': picked, 'new': named['new'], 'filed': filed}) + '\n')
    lister.save()
    save(store)
    logger.info("Watch list: %d plain claims filed again (%s), %d watched", sum(outcomes.values()), dict(outcomes),
                sum(1 for w in store['claims'].values() if w.get('plain')))
    return dict(outcomes)


def told_later() -> list[dict]:
    """Every plain report later told as a motif: {claim, reported (t0), at (t1), was, motifs}, oldest first"""
    try:
        with open(REFILE_LOG) as f:
            rows = [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []
    return [{'claim': r['claim'], 'reported': r.get('reported'), 'at': r['at'], 'was': r['was'], 'motifs': r['filed']}
            for r in rows if r.get('filed')]
