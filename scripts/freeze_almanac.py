"""Freeze the Election Almanac (app/site/almanac_2026.json): record the SHA-256 of its forecast and the time, once.

Run it after the last tuning, before Nov 3 00:00 Eastern, then commit the file:

    .venv/bin/python scripts/freeze_almanac.py

It refuses to run on a forecast already frozen. After freezing, any edit to the forecast breaks its seal: the page
stops scoring it and says so, and tests/test_almanac.py fails, so the pre-commit hook refuses the edit. Only
`results.house` (who won the House, as AP calls it) may be set afterwards; it sits outside the seal."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis import almanac  # noqa: E402


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else almanac.FORECAST
    try:
        seal = almanac.freeze(path)
    except RuntimeError as e:
        print(f'Not frozen: {e}', file=sys.stderr)
        return 1
    print(f"Frozen at {seal['at']}\nSHA-256 {seal['sha256']}")
    if seal['late']:
        print('Warning: frozen after the deadline (Nov 3, 00:00 Eastern); the page says so.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
