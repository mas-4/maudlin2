#!/bin/bash
# One scrape and build. Production (the clone systemd runs, ~/maudlin-prod) first pulls main, so what runs is what was
# pushed: commits pass the test suite in a pre-commit hook and CI runs a smoke check. When the pull brings new
# requirements or C code it reinstalls or rebuilds, and it applies any database migrations. If the pull fails, it runs
# the code it already has. The working tree is left alone when it has uncommitted changes (a dev checkout).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if git diff --quiet && git diff --cached --quiet; then
    before="$(git rev-parse HEAD)"
    if git pull --ff-only -q origin main; then
        after="$(git rev-parse HEAD)"
        if [ "$before" != "$after" ]; then
            changed="$(git diff --name-only "$before" "$after")"
            echo "Pulled ${before:0:7}..${after:0:7}"
            if grep -qx 'requirements.txt' <<< "$changed"; then
                .venv/bin/pip install -q -r requirements.txt
            fi
            if grep -qE '\.c$|^setup\.py$' <<< "$changed"; then
                .venv/bin/python setup.py -q build_ext --inplace
            fi
        fi
    else
        echo "git pull failed; running the code already checked out" >&2
    fi
fi

# Did the timer wake the machine for this run? (the kernel logs the resume just before the timer fires)
woke=0
if journalctl -q -k --since "-5min" 2>/dev/null | grep -q "PM: suspend exit"; then
    woke=1
fi

.venv/bin/alembic upgrade head || { echo "Database migration failed; not running" >&2; exit 1; }
.venv/bin/python main.py --run-selenium
status=$?

# Back to sleep if the timer woke the machine and nobody has come back to it: the desktop locks the screen before
# sleeping, so a session still locked after the run means no one's using it. Otherwise it'd sit awake until the
# desktop's own idle timer, about 45 minutes of every hour overnight.
if [ "$woke" = 1 ]; then
    locked=$(for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
        loginctl show-session "$s" -p Type -p LockedHint --value | paste -sd' '
    done | awk '$1 == "wayland" || $1 == "x11" {print $2}' | sort -u)
    if [ "$locked" = "yes" ]; then
        echo "Woken by the timer and still locked: suspending"
        systemctl suspend || echo "Suspend not allowed for this service (see logind/polkit)" >&2
    fi
fi
exit $status
