#!/bin/bash
# Bring production (~/maudlin-prod) up to main now, without waiting for the hourly run (Oct 18, the person: "is there
# any way we can make a manual intervention to manually pull changes in prod ... instead of waiting forever"). The
# same pull the hourly run makes first (scripts/run.sh), and then the services that follow the code pick it up on
# their own: the checker within a minute, the worker after its current cycle, the deck and lights at their restart.
#
# It waits for the hourly run instead when:
#   - the run is going (code changing under a running build)
#   - the new commits bring a database migration (the run applies those, before anything uses the new code)
#   - production has uncommitted changes
#
#   scripts/update_prod.sh
set -uo pipefail

PROD="$HOME/maudlin-prod"
cd "$PROD" || exit 1

state="$(systemctl show maudlin-scrape -p ActiveState --value)"
if [ "$state" = active ] || [ "$state" = activating ]; then
    echo "The hourly run is going: it pulls main itself; try again when it's done" >&2
    exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet; then
    echo "$PROD has uncommitted changes: not pulling" >&2
    exit 1
fi

git fetch -q origin main || { echo "git fetch failed" >&2; exit 1; }
before="$(git rev-parse HEAD)"
after="$(git rev-parse origin/main)"
if [ "$before" = "$after" ]; then
    echo "Production is already at ${after:0:7}"
    exit 0
fi
changed="$(git diff --name-only "$before" "$after")"
if grep -q '^alembic/versions/' <<< "$changed"; then
    echo "The new commits bring a database migration: leaving them to the hourly run, which applies it" >&2
    exit 1
fi

git merge --ff-only -q "$after" || { echo "Not a fast-forward: not pulling" >&2; exit 1; }
echo "Pulled ${before:0:7}..${after:0:7}"
git log --oneline "$before..$after" | sed 's/^/  /'
if grep -qx 'requirements.txt' <<< "$changed"; then
    .venv/bin/pip install -q -r requirements.txt
fi
if grep -qE '\.c$|^setup\.py$' <<< "$changed"; then
    .venv/bin/python setup.py -q build_ext --inplace
fi
echo "The checker restarts on it within a minute; the worker after its current cycle"
