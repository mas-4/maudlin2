"""The list of scrapers to check after each run."""
import json

import pytest

from app import scraper_health as sh


def run(found=50, kept=50, added=5, too_long=0, error=None):
    return {'at': 't', 'url': 'u', 'found': found, 'kept': kept, 'added': added, 'too_long': too_long, 'error': error}


@pytest.mark.parametrize('now, past, says', [
    (run(), [run()] * 10, []),
    (run(error='ConnectionError'), [], ["page didn't load (ConnectionError)"]),
    (run(error='page not loaded'), [run(error='x')] * 2, ["page didn't load (page not loaded), 3 runs in a row"]),
    (run(found=0, kept=0), [run()] * 10, ['found no headlines (usually 50)']),
    (run(found=40, kept=0), [run()] * 10, ['found 40 but kept none: the parser may be picking the wrong elements']),
    (run(found=10, kept=10), [run()] * 10, ['found 10, usually 50']),
    (run(found=10, kept=10), [run()] * 3, []),  # too little history to know what's usual
    (run(found=40, kept=10, too_long=30), [run()] * 10,
     ['dropped 30 of 40 as too long: the parser may be grabbing summaries']),
    (run(added=0), [run(added=0)] * (sh.STALE_RUNS - 1), [f'no new headline in {sh.STALE_RUNS} runs: the page may be stuck or cached']),
    (run(added=0), [run(added=0)] * 30, []),  # a quiet day isn't stale
])
def test_problems(now, past, says):
    assert sh.problems('X', now, past) == says


def test_write_lists_flagged_and_missing_scrapers(monkeypatch, tmp_path):
    monkeypatch.setattr(sh, 'HISTORY_FILE', str(tmp_path / 'history.json'))
    monkeypatch.setattr(sh, 'CHECK_FILE', str(tmp_path / 'check.md'))
    sh.record('Good', 'https://good', found=40, kept=40, added=3)
    sh.record('Empty', 'https://empty', found=0)
    flagged = sh.write([('Good', 'https://good'), ('Empty', 'https://empty'), ('Crashed', 'https://crashed')])
    assert [a for a, _ in flagged] == ['Crashed', 'Empty']
    text = (tmp_path / 'check.md').read_text()
    assert "**Crashed** (https://crashed): page didn't load (never finished)" in text
    assert '**Empty**' in text and 'Good' not in text
    assert len(json.loads((tmp_path / 'history.json').read_text())['Good']) == 1
    sh.record('Good', 'https://good', found=40, kept=40, added=3)
    assert sh.write([('Good', 'https://good')]) == []
    assert 'All 1 scrapers look healthy.' in (tmp_path / 'check.md').read_text()
