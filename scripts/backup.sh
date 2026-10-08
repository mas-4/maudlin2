#!/bin/bash
# Daily backup to a different physical drive than the one the data lives on: the database, and as a tar every other
# data file that can't be rebuilt (the hand curation, judgment caches, collected posts, run state).
# Uses SQLite's online backup so it's safe while a scrape is writing, then gzips and prunes old copies.
# To restore the files: tar -xzf files-<date>.tar.gz -C <data folder> (stop the hourly timer first).
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
    FILES="$DEST/files-$(date +%Y-%m-%d-%H%M).tar.gz"
else
    FILES="$DEST/files-$(date +%Y-%m-%d).tar.gz"
fi
RUN_KEEP="${MAUDLIN_RUN_BACKUPS:-48}"  # two days of hourly copies (Oct 8; 5 until then)

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

# The other data files. Left out: the database (above) and what's rebuilt on demand (embedding caches, motif
# vectors, the log). The collected posts (vernacular.sqlite) go in the nightly copy only, through SQLite's online
# backup; the hourly copy is the small hand-curation set, so a day's curation is never more than an hour from a copy.
DATA="$ROOT/data"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
EXTRA=()
# The curation database (motif index versions, saved states, the curation log), every time, through SQLite's online
# backup: tarred while the checker writes it, the file could be caught half-written
if [ -f "$DATA/curation.sqlite" ]; then
    "$ROOT/.venv/bin/python" - "$DATA/curation.sqlite" "$TMP/curation.sqlite" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
    EXTRA+=(-C "$TMP" curation.sqlite)
fi
if [ "${1:-}" != "run" ] && [ -f "$DATA/vernacular.sqlite" ]; then
    "$ROOT/.venv/bin/python" - "$DATA/vernacular.sqlite" "$TMP/vernacular.sqlite" <<'PY'
import sqlite3, sys
src, dst = sqlite3.connect(sys.argv[1]), sqlite3.connect(sys.argv[2])
with dst:
    src.backup(dst)
dst.close(); src.close()
PY
    EXTRA+=(-C "$TMP" vernacular.sqlite)
fi
tar -czf "$FILES" -C "$DATA" --exclude=./data.db --exclude=./vernacular.sqlite --exclude='./curation.sqlite*' \
    --exclude='*embeddings.sqlite' \
    --exclude=./motifs/vectors.npy --exclude='./app.log*' --exclude='*.lock' --exclude='*.tmp' . "${EXTRA[@]}"
if [ "${1:-}" = "run" ]; then
    ls -1t "$DEST"/files-*.tar.gz | tail -n +"$((RUN_KEEP + 1))" | xargs -r rm -f
else
    find "$DEST" -maxdepth 1 -name 'files-*.tar.gz' -mtime +"$KEEP_DAYS" -delete
fi
echo "Backed up the other data files to $FILES ($(du -h "$FILES" | cut -f1))"
