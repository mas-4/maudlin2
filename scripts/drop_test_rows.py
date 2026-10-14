"""Take the test suite's rows out of the shortlist and filing logs (Oct 14). Until then the suite wrote its fake
filings into the real logs (tests/conftest.py now prevents it): 624 of the shortlist log's 867 rows on Oct 14, every
one with 'next' (the index's next motif number) of 2 or less, where the real index's is 879 and up; and the filing
log's rows written in the same seconds. Each log is copied whole beside itself first (*.with-test-rows-<day>.jsonl).
Filing-log rows from before Oct 12, when the shortlist log began, can't be told apart and stay.

    python scripts/drop_test_rows.py           what it would take out
    python scripts/drop_test_rows.py --apply   take them out"""
import json
import os
import shutil
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.analysis import motif_index as mi  # noqa: E402

TEST_NEXT = 2  # the test indexes' highest next motif number


def main(apply: bool):
    with open(mi.SHORTLIST_LOG) as f:
        short = f.readlines()
    with open(mi.FILING_LOG) as f:
        filing = f.readlines()
    rows = [json.loads(line) for line in short]
    seconds = {r['at'] for r in rows if r.get('next', 0) <= TEST_NEXT}
    keep_short = [line for line, r in zip(short, rows) if r.get('next', 0) > TEST_NEXT]
    keep_filing = [line for line in filing if json.loads(line).get('at') not in seconds]
    print(f'shortlist log: {len(short)} rows, {len(short) - len(keep_short)} from tests')
    print(f'filing log: {len(filing)} rows, {len(filing) - len(keep_filing)} from tests')
    if not apply:
        print('nothing changed: run with --apply to take them out')
        return
    for path, keep in ((mi.SHORTLIST_LOG, keep_short), (mi.FILING_LOG, keep_filing)):
        shutil.copy2(path, path.replace('.jsonl', f'.with-test-rows-{date.today()}.jsonl'))
        with open(path + '.tmp', 'w') as f:
            f.writelines(keep)
        os.replace(path + '.tmp', path)
    print('done; the originals are kept beside them')


if __name__ == '__main__':
    main('--apply' in sys.argv)
