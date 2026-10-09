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

# A copy of the database before anything touches it (the newest 5 are kept; nightly copies are separate)
scripts/backup.sh run || echo "Backup before the run failed; running anyway" >&2

.venv/bin/alembic upgrade head || { echo "Database migration failed; not running" >&2; exit 1; }
# Keep the machine awake while the run works. On Oct 5 the desktop's idle timer suspended it at 3:04, in the middle
# of GPU transcription; it never resumed, and 4 hourly runs were lost until a cold boot at 7:10. The desktop (KDE)
# is what suspends, and it honors a request from any program of the same user over the session bus, no polkit
# needed; kde-inhibit always exits 0, so the run's own status goes through a file. Without the bus (no one logged
# in) it runs as before.
status_file="$(mktemp)"
echo 1 > "$status_file"
bus="/run/user/$(id -u)/bus"
if [ -S "$bus" ] && command -v kde-inhibit >/dev/null; then
    DBUS_SESSION_BUS_ADDRESS="unix:path=$bus" kde-inhibit --power \
        sh -c '.venv/bin/python main.py --run-selenium; echo $? > "$1"' sh "$status_file"
else
    .venv/bin/python main.py --run-selenium
    echo $? > "$status_file"
fi
status=$(cat "$status_file")
rm -f "$status_file"

# Back to sleep if the timer woke the machine and nobody has come back to it: the desktop locks the screen before
# sleeping, so a session still locked after the run means no one's using it. Otherwise it'd sit awake until the
# desktop's own idle timer, about 45 minutes of every hour overnight.
if [ "$woke" = 1 ]; then
    locked=$(for s in $(loginctl list-sessions --no-legend | awk '{print $1}'); do
        loginctl show-session "$s" -p Type -p LockedHint --value | paste -sd' '
    done | awk '$1 == "wayland" || $1 == "x11" {print $2}' | sort -u)
    # The worker in the middle of a cycle keeps the machine awake itself (app/worker.py); it lets it sleep when done
    worker_busy=$(.venv/bin/python -c 'from app import worker; print(int(worker.busy()))' 2>/dev/null || echo 0)
    if [ "$locked" = "yes" ] && [ "$worker_busy" = 1 ]; then
        echo "Woken by the timer and still locked, but the worker is busy: not suspending"
    elif [ "$locked" = "yes" ]; then
        echo "Woken by the timer and still locked: suspending"
        systemctl suspend || echo "Suspend not allowed for this service (see logind/polkit)" >&2
    fi
fi
exit $status
