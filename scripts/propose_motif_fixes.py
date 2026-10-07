"""Propose fixes to the motif index (app/analysis/motif_proposals.py): typos, kind-of and related links, merges and
group memberships, and links already made that look wrong, for a person to approve or reject in the workbench's 💡 proposals tab. Uses the GPU, so it waits
for a quiet moment (not during the hourly run or its first 15 minutes).

    .venv/bin/python scripts/propose_motif_fixes.py                # all kinds
    .venv/bin/python scripts/propose_motif_fixes.py typos links    # some of them
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis import motif_proposals  # noqa: E402


def quiet():
    while True:
        state = subprocess.run(['systemctl', 'show', '-p', 'ActiveState', '--value', 'maudlin-scrape.service'],
                               capture_output=True, text=True).stdout.strip()
        if state == 'inactive' and 16 <= datetime.now().minute < 50:
            return
        time.sleep(30)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('kinds', nargs='*', choices=['typos', 'links', 'review', 'groups'], default=['typos', 'links', 'review', 'groups'])
    args = ap.parse_args()
    for kind in args.kinds:  # one kind at a time, each in a quiet stretch
        quiet()
        print(kind, motif_proposals.propose((kind,)), flush=True)
