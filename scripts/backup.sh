#!/bin/bash
# Daily database backup to a different physical drive than the one the database lives on.
# Uses SQLite's online backup so it's safe while a scrape is writing, then gzips and prunes old copies.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SOURCE="$ROOT/data/data.db"
DEST="${MAUDLIN_BACKUP_DIR:-/data/ssd1t/maudlin-backups}"
KEEP_DAYS="${MAUDLIN_BACKUP_KEEP_DAYS:-30}"
TARGET="$DEST/data-$(date +%Y-%m-%d).db"
# `backup.sh run`: the copy every hourly run takes first, in its own folder, keeping only the newest RUN_KEEP
if [ "${1:-}" = "run" ]; then
    DEST="$DEST/runs"
    TARGET="$DEST/data-$(date +%Y-%m-%d-%H%M).db"
fi
RUN_KEEP="${MAUDLIN_RUN_BACKUPS:-5}"

mkdir -p "$DEST"
"$ROOT/.venv/bin/python" - "$SOURCE" "$TARGET" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
gzip -f "$TARGET"
if [ "${1:-}" = "run" ]; then
    ls -1t "$DEST"/data-*.db.gz | tail -n +"$((RUN_KEEP + 1))" | xargs -r rm -f
else
    find "$DEST" -maxdepth 1 -name 'data-*.db.gz' -mtime +"$KEEP_DAYS" -delete
fi
echo "Backed up to $TARGET.gz ($(du -h "$TARGET.gz" | cut -f1))"
