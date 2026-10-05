"""Read back a person's recent curation of the motif index, for whoever is helping them (the curation log,
data/validation/curation_log.jsonl): each change since the last review, with the claim it moved, the motifs' names
before and now, and flags on names that break the naming rules (the debunker's frame, an analyst's label, a sentence).

    .venv/bin/python scripts/review_curation.py           # changes since the last review, then marks them reviewed
    .venv/bin/python scripts/review_curation.py --all     # every live (not rebuilt) change today
    .venv/bin/python scripts/review_curation.py --keep    # don't move the mark
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis import motif_index as mi  # noqa: E402
from app.utils import Config  # noqa: E402

LOG = os.path.join(Config.data, 'validation', 'curation_log.jsonl')
MARK = os.path.join(Config.data, 'validation', 'review_mark')
# Words that name the debunking or an analyst's view rather than the story as its tellers tell it
FRAME = re.compile(r'myth|hoax|false|fake|fabricat|misattribut|misrepresent|mislead|misinformation|disinformation|'
                   r'deepfake|ai-generated|debunk|narrative|rumou?r|controversy|accusation|claims?\b', re.I)


def flags(name: str) -> list[str]:
    out = []
    if FRAME.search(name):
        out.append('frame word (' + FRAME.search(name).group(0) + ')')
    if len(name.split()) > mi.MAX_WORDS:
        out.append('long')
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--keep', action='store_true')
    args = ap.parse_args()
    since = '' if args.all else (open(MARK).read().strip() if os.path.exists(MARK) else '')
    index = mi.load()
    entries = index['entries']
    rows = [json.loads(line) for line in open(LOG)]
    rows = [r for r in rows if not r.get('reconstructed') and r['at'] > since]
    mine = [r for r in rows if not r.get('by')]  # the person's own; 'by' marks changes others made with approval
    print(f'{len(mine)} change(s) by the person since {since or "the start"} ({len(rows) - len(mine)} by others)\n')
    for r in mine:
        a, before = r['action'], r.get('before') or {}
        name_was = lambda k: (before.get(k) or {}).get('name') if isinstance(before.get(k), dict) else None  # noqa: E731
        now = lambda i: entries.get(i, {}).get('name') if i in entries else None  # noqa: E731
        parts = []
        for k in ('id', 'source', 'target', 'a', 'b', 'child', 'parent'):
            if a.get(k) and str(a[k]).startswith('M'):
                was, cur = name_was(k), now(a[k])
                parts.append(f'{k} {a[k]} “{was or cur}”' + (f' (now “{cur}”)' if cur and was and cur != was else ''))
        print(f"{r['at'][11:19]} {r['page']}: {a.get('action')}  " + '; '.join(parts))
        if a.get('claim'):
            print(f"    claim: {a['claim'][:160]}")
        for k in ('name', 'text'):
            if a.get(k):
                print(f"    {k}: “{a[k]}”" + ('   ⚑ ' + ', '.join(flags(a[k])) if flags(a[k]) else ''))
        target = a.get('id') if a.get('action') in ('rename', 'done') else None
        if a.get('action') in ('also_new', 'move_new', 'add') and a.get('name'):
            target = next((e['id'] for e in mi.live(index) if e['name'] == a['name']), None)
        if target and target in entries and not entries[target].get('merged_into'):
            e = entries[target]
            print(f"    {target} “{e['name']}” now holds {len(e['claims'])}: " +
                  ' | '.join(c['claim'][:70] for c in e['claims'][:4]))
    if rows and not args.keep and not args.all:
        with open(MARK, 'w') as f:
            f.write(rows[-1]['at'])


if __name__ == '__main__':
    main()
