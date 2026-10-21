"""Cordelia's weekly measure (papers/cordelia.md): are claims written since the wording change (Oct 12, about 11:05)
shorter, does the person reword fewer of the ones they judge, and is nothing lost on the way? Read from the logs alone,
no model: the shortlist log (each claim as first written), the index and its corrections, the curation log, the
shows' and the Focus Group's kept and dropped claims, and the filing log.

    .venv/bin/python scripts/experiments/cordelia_measure.py          # print the measure as Markdown
    .venv/bin/python scripts/experiments/cordelia_measure.py --log    # and add a line to cordelia.jsonl

Written Oct 21 after the first measure (done by hand) found hypothesis 2 confounded: the person had judged almost
nothing that week, so "reworded none of the new claims" said little. Here the rewording share is taken over the claims
the person judged, before and after alike."""
import argparse
import json
import os
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime as dt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402
from app.utils.store import read_json  # noqa: E402

CHANGE = '2026-10-12T11:05'
BEFORE = ('2026-10-05', '2026-10-12')  # claims dated in these days, not in the shortlist log, are the baseline
LOG = os.path.join(Config.data, 'motifs', 'experiments', 'cordelia.jsonl')
# The person's decisions on a claim (Claude's own rows, and those it made on the person's word, left out)
JUDGING = {'check', 'unfile', 'move', 'also', 'correct', 'reject', 'not this motif', 'reviewed, kept', 'no_motif', 'file',
           'also_new', 'move_new', 'split', 'hold'}


def kind(source: str) -> str:
    return {'narrative': 'posts', 'shows': 'shows', 'Focus Group': 'Focus Group'}.get(source, 'fact-checks')


def words(text: str) -> int:
    return len(text.split())


def jsonl(path: str) -> list[dict]:
    try:
        with open(path) as f:
            return [json.loads(line) for line in f if line.strip()]
    except OSError:
        return []


def originals(corrections: dict) -> dict[str, set[str]]:
    """Each claim's earlier wordings, through chains of corrections (a correction of a correction)"""
    back = defaultdict(set)
    for old, new in corrections.items():
        back[new].add(old)
    out = {}
    for new in back:
        seen, todo = set(), list(back[new])
        while todo:
            t = todo.pop()
            if t not in seen:
                seen.add(t)
                todo += back.get(t, [])
        out[new] = seen
    return out


def decisions(rows: list[dict]) -> list[tuple[str, str, str]]:
    """(when, action, claim text) for each of the person's decisions on a claim, batch steps opened"""
    out = []

    def walk(a: dict, at: str):
        if not isinstance(a, dict):
            return
        if a.get('action') == 'batch':
            for s in a.get('steps') or []:
                walk(s, at)
        elif a.get('action') in JUDGING and isinstance(a.get('claim'), str):
            out.append((at, a['action'], a['claim']))
    for r in rows:
        if r.get('by') is None:
            walk(r.get('action'), r.get('at') or '')
    return out


def measure() -> dict:
    index = mi.load()
    back = originals(index.get('corrections', {}))
    first = {}  # claim key (as first written) -> {'claim', 'source', 'at'}
    for r in jsonl(mi.SHORTLIST_LOG):
        if r.get('at', '') >= CHANGE and r.get('key') not in first:
            first[r['key']] = {'claim': r['claim'], 'source': r.get('source', ''), 'at': r['at']}
    logged = {r.get('key') for r in jsonl(mi.SHORTLIST_LOG)}
    before = {}
    for e in index['entries'].values():
        for c in e.get('claims', []):
            if not BEFORE[0] <= (c.get('date') or '') <= BEFORE[1]:
                continue
            olds = back.get(c['claim'], set())
            original = min(olds, key=len) if olds else c['claim']  # as first written, before any rewording
            k = mi.key(original)
            if k not in logged and mi.key(c['claim']) not in logged:
                before.setdefault(k, {'claim': original, 'source': c.get('source', ''), 'at': c.get('date')})
    # Every key a decision's claim text may have had
    judged, reworded = set(), set()
    for _at, act, text in decisions(jsonl(os.path.join(Config.data, 'validation', 'curation_log.jsonl'))):
        keys = {mi.key(text)} | {mi.key(o) for o in back.get(text, set())}
        judged |= keys
        if act == 'correct':
            reworded |= keys
    out = {'at': dt.now().isoformat(timespec='seconds'), 'by_source': {}}
    for name, group in (('after', first), ('before', before)):
        by = defaultdict(list)
        for k, c in group.items():
            by[kind(c['source'])].append((k, c))
        for src, items in by.items():
            row = out['by_source'].setdefault(src, {})
            seen = [k for k, _ in items if k in judged]
            row[name] = {'claims': len(items), 'mean words': round(statistics.mean(words(c['claim']) for _, c in items), 1),
                         'judged': len(seen), 'reworded': sum(1 for k in seen if k in reworded)}
    # Nothing lost: quotes kept by the shows and the Focus Group, before and after; the filing's "nothing fits"
    lost = {}
    for name, path in (('shows', 'show_claims.json'), ('Focus Group', 'focus_group_claims.json')):
        tally = {'after': Counter(), 'before': Counter()}
        for ep in read_json(os.path.join(Config.data, path), {}).values():
            when = 'after' if (ep.get('date') or '') > CHANGE[:10] else 'before' if (ep.get('date') or '') >= BEFORE[0] else None
            if when is None:
                continue
            tally[when]['kept'] += len(ep.get('claims', []))
            for d in ep.get('dropped', []):
                why = d.get('why') or ''
                tally[when]['unsupported' if 'support' in why else 'quote not found' if 'quote' in why else 'other'] += 1
        lost[name] = {w: dict(t) for w, t in tally.items()}
    fits = {'after': Counter(), 'before': Counter()}
    for r in jsonl(os.path.join(Config.data, 'motifs', 'filing_log.jsonl')):
        when = 'after' if r.get('at', '') >= CHANGE else 'before' if r.get('at', '') >= BEFORE[0] else None
        if when:
            fits[when].update({k: v for k, v in r.items() if k in ('matched', 'new', 'none')})
    out['quotes'] = lost
    out['filing'] = {w: dict(c) for w, c in fits.items()}
    return out


def pct(a: int, b: int) -> str:
    return f'{100 * a / b:.1f}%' if b else '—'


def markdown(m: dict) -> str:
    lines = [f"Cordelia, measured {m['at'][:16]} (claims written since {CHANGE.replace('T', ' ')}, against those dated "
             f"{BEFORE[0]} to {BEFORE[1]})", '',
             '| source | after: claims, mean words | before | after: reworded of judged | before: reworded of judged |',
             '|---|---|---|---|---|']
    for src in ('posts', 'shows', 'Focus Group', 'fact-checks'):
        r = m['by_source'].get(src, {})
        a, b = r.get('after'), r.get('before')
        cell = lambda x: f"{x['claims']}, {x['mean words']}" if x else 'none'  # noqa: E731
        rew = lambda x: f"{x['reworded']} of {x['judged']} ({pct(x['reworded'], x['judged'])})" if x else ''  # noqa: E731
        lines.append(f'| {src} | {cell(a)} | {cell(b)} | {rew(a)} | {rew(b)} |')
    lines += ['', '| quotes | kept after | dropped after (not found, unsupported) | kept before | dropped before |',
              '|---|---|---|---|---|']
    for src, t in m['quotes'].items():
        a, b = t.get('after', {}), t.get('before', {})
        drop = lambda x: f"{x.get('quote not found', 0)}, {x.get('unsupported', 0)}"  # noqa: E731
        lines.append(f"| {src} | {a.get('kept', 0)} | {drop(a)} | {b.get('kept', 0)} | {drop(b)} |")
    f = m['filing']
    share = lambda c: pct(c.get('none', 0), sum(c.values()))  # noqa: E731
    lines += ['', f"Filing, nothing fits: {share(f.get('after', {}))} of {sum(f.get('after', {}).values())} claims after, "
              f"{share(f.get('before', {}))} of {sum(f.get('before', {}).values())} before."]
    return '\n'.join(lines)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--log', action='store_true', help='add the measure to motifs/experiments/cordelia.jsonl')
    args = p.parse_args()
    m = measure()
    print(markdown(m))
    if args.log:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, 'a') as f:
            f.write(json.dumps(m) + '\n')
