"""F12 Prometheus and F13 Persephone: the shortlist forward (Oct 12, from Fable's review). Production logs what each
new claim was shown and what the filing model picked, before anyone judged it (motif_index.SHORTLIST_LOG). Weekly,
each logged claim's motifs by the person's final word (the motifs it's in now and checked) are sorted three ways:

    shown                    the motif existed and was among those shown
    existed, not shown       the motif existed (its number under the log's 'next') but the shortlist missed it
    made later               the person made the motif after the claim arrived: no shortlist could have shown it

and the seeds (Persephone): how often a seed was shown, picked, and kept. Read only, CPU; the papers are
~/maudlin-data/papers/prometheus.md and persephone.md.

    f12_prometheus.py [days]      the last `days` of the log (default 7), into the log and the catalog"""
import json
import os
import sys
from datetime import datetime as dt
from datetime import timedelta as td

sys.path.insert(0, '/home/mas/Repos/maudlin2/scripts/experiments')
import harness  # noqa: E402

sys.path.insert(0, '/home/mas/Repos/maudlin2')
from app.analysis import motif_index as mi  # noqa: E402

OUT = os.path.join(harness.EXP, 'f12_prometheus.json')


def number(eid: str) -> int:
    return int(eid.lstrip('M')) if eid.lstrip('M').isdigit() else -1


def main():
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    since = (dt.now() - td(days=days)).isoformat()
    try:
        rows = [json.loads(x) for x in open(mi.SHORTLIST_LOG) if x.strip()]
    except OSError:
        rows = []
    rows = [r for r in rows if r['at'] >= since]
    index = mi.load()
    final = {}  # claim key -> the motifs the person has kept it in
    for e in mi.live(index):
        for c in e['claims']:
            if c.get('checked') == 'yes':
                final.setdefault(mi.key(c['claim']), set()).add(e['id'])
    judged = [r for r in rows if r['key'] in final]
    shown = existed_missed = later = 0
    for r in judged:
        for m in final[r['key']]:
            if m in r['shown']:
                shown += 1
            elif number(m) < r['next']:
                existed_missed += 1
            else:
                later += 1
    total = shown + existed_missed + later
    seeds_shown = sum(len(r.get('seeds', [])) for r in rows)
    seeds_picked = sum(1 for r in rows for m in r.get('picked', []) if m in r.get('seeds', []))
    seeds_kept = sum(1 for r in judged for m in r.get('picked', []) if m in r.get('seeds', []) and m in final[r['key']])
    out = {'since': since, 'logged': len(rows), 'judged': len(judged), 'motifs': total, 'shown': shown,
           'existed, not shown': existed_missed, 'made later': later,
           'seeds shown': seeds_shown, 'seeds picked': seeds_picked, 'seeds kept': seeds_kept}
    json.dump(out, open(OUT, 'w'), indent=1)
    pct = (lambda n: f'{n / total:.0%}') if total else (lambda n: '–')  # noqa: E731
    line = (f"F12 Prometheus: {len(rows)} new claims logged in {days} days, {len(judged)} with the person's final word "
            f"({total} motifs): shown {shown} ({pct(shown)}), existed but not shown {existed_missed} ({pct(existed_missed)}), "
            f"made later {later} ({pct(later)}); F13 Persephone: seeds shown {seeds_shown} times, picked {seeds_picked}, "
            f"kept {seeds_kept}")
    print(line, flush=True)
    harness.note(line)


if __name__ == '__main__':
    main()
