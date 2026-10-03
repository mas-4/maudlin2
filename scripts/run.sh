#!/bin/bash
# One scrape and build, reporting to a dead man's switch if one is configured: put a ping url (e.g. from
# healthchecks.io) in .healthcheck_creds and you'll be emailed when runs fail or stop happening at all.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PING=""
[ -f "$ROOT/.healthcheck_creds" ] && PING="$(tr -d '[:space:]' < "$ROOT/.healthcheck_creds")"
ping() { [ -n "$PING" ] && curl -fsS -m 10 --retry 3 -o /dev/null "$PING$1" || true; }

ping /start
cd "$ROOT" && "$ROOT/.venv/bin/python" main.py --run-selenium
status=$?
if [ $status -eq 0 ]; then ping ""; else ping /fail; fi
exit $status
