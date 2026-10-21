"""Psyche's splits offered in the ✂️ tab (papers/psyche.md). Psyche's forward step read production's claims but wrote
its split proposals into the experiments' copy of the data, so the 45 it drafted never reached the person. This puts
them in production's proposals as open splits, each as the organizer drafted it on Oct 16, leaving out claims that are
no longer filed, have been split already, or were asked about since.

    .venv/bin/python scripts/experiments/psyche_offer.py           # list what would be offered
    .venv/bin/python scripts/experiments/psyche_offer.py --apply   # offer them (the person's call)

Written Oct 21 from the BND3 handoff ("Psyche's 45 split proposals went to the lab copy and never reached ✂️")."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.analysis import claim_organizer as co  # noqa: E402
from app.analysis import motif_index as mi  # noqa: E402
from app.analysis import motif_proposals as mp  # noqa: E402
from app.utils import Config  # noqa: E402
from app.utils.store import read_json  # noqa: E402

PSYCHE = os.path.join(Config.data, 'motifs', 'experiments', 'f22_psyche.json')


def drafted() -> list[dict]:
    """Psyche's forward readings that drafted a split: [{'read': organize()'s result, 'triggers': ...}]"""
    return [v for v in read_json(PSYCHE, {}).get('forward', {}).values() if (v.get('read') or {}).get('split')]


def offer(apply: bool = False) -> tuple[list[str], list[tuple[str, str]]]:
    """(claims offered, [(claim, why left out)])"""
    index, store = mi.load(), mp.load()
    offered, left = [], []
    for v in drafted():
        r = v['read']
        k = mi.key(r['claim'])
        if not mi._ids(index, k):
            left.append((r['claim'], 'no longer filed'))
        elif k in index.get('tellings', {}):
            left.append((r['claim'], 'split already'))
        elif co.asked(store, r['claim'], r['motifs']):
            left.append((r['claim'], 'asked about since'))
        else:
            co.propose(store, r, v.get('triggers'))
            offered.append(r['claim'])
    if apply and offered:
        mp.save(store)
    return offered, left


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--apply', action='store_true', help="put them in production's proposals (the ✂️ tab)")
    args = p.parse_args()
    offered, left = offer(args.apply)
    print(f"{'Offered' if args.apply else 'Would offer'} {len(offered)} of {len(drafted())} drafted splits")
    for c in offered:
        print('  +', c[:140])
    for c, why in left:
        print(f'  - {c[:120]} ({why})')
