"""Import for the narratives group (see scripts/json_import/__init__.py): the narrative reports
(narratives/report-*.json; their .md copies are left as they are), narratives/withheld.json, narratives/threads.json
(its days into rows, the reports it linked marked, the model's verdicts into the cache) and chyrons/matched-*.json."""
import glob
import os

from sqlalchemy import insert

from app.tables.narratives import (MATCH_FIELDS, ChyronMatch, NarrativeGroup, NarrativeReport, NarrativeThreadDay,
                                   NarrativeWithheld, group_rows, report_row)
from app.utils.store import read_json, write_json


def run(session, data: str, cache: str) -> dict:
    counts = {'reports': 0, 'groups': 0, 'withheld': 0, 'thread_days': 0, 'linked': 0, 'verdicts': 0,
              'chyron_days': 0, 'chyron_matches': 0}
    folder = os.path.join(data, 'narratives')
    files = []
    for path in sorted(glob.glob(os.path.join(folder, 'report-*.json'))):
        report = read_json(path, None)
        if not isinstance(report, dict):
            continue
        file = os.path.basename(path)
        session.execute(insert(NarrativeReport), [report_row(file, report)])
        rows = group_rows(file, report.get('found', []))
        if rows:
            session.execute(insert(NarrativeGroup), rows)
        files.append(file)
        counts['groups'] += len(rows)
    counts['reports'] = len(files)

    withheld = {w['claim']: w for w in read_json(os.path.join(folder, 'withheld.json'), []) if w.get('claim')}
    if withheld:
        session.execute(insert(NarrativeWithheld), [{'claim': c, 'reason': w.get('reason', ''), 'at': w.get('at', '')}
                                                    for c, w in withheld.items()])
    counts['withheld'] = len(withheld)

    threads = read_json(os.path.join(folder, 'threads.json'), {})
    days = [{'thread': tid, 'report': d['report'], 'date': d['date'], 'claim': d['claim'], 'people': d.get('people'),
             'posts': d.get('posts'), 'genre': d.get('genre') or '', 'story': d.get('story')}
            for tid, t in sorted((threads.get('threads') or {}).items()) for d in t.get('days', [])]
    if days:
        session.execute(insert(NarrativeThreadDay), days)
    counts['thread_days'] = len(days)
    linked = [f for f in threads.get('linked') or [] if f in files]
    if linked:
        session.query(NarrativeReport).filter(NarrativeReport.file.in_(linked)) \
            .update({'threads_linked': True}, synchronize_session=False)
    counts['linked'] = len(linked)
    verdicts = threads.get('verdicts') or {}
    target = os.path.join(cache, 'narratives', 'thread_verdicts.json')
    if verdicts and not os.path.exists(target):  # part of threads.json, so copied out, not moved
        write_json(target, verdicts)
    counts['verdicts'] = len(verdicts)

    for path in sorted(glob.glob(os.path.join(data, 'chyrons', 'matched-*.json'))):
        day = os.path.basename(path)[len('matched-'):-len('.json')]
        rows = [{'day': day, **{f: c.get(f) for f in MATCH_FIELDS}} for c in read_json(path, []) or []]
        if rows:
            session.execute(insert(ChyronMatch), rows)
        counts['chyron_days'] += 1
        counts['chyron_matches'] += len(rows)
    return counts
