#!/usr/bin/env bash
# Daily finnspark database backup — keeps the last 14 dumps (≈ 2 weeks of daily
# restore points). Runs from cron; uses the SQLite online-backup API so the
# backup is consistent even while the backend is writing.
set -euo pipefail

BACKUP_DIR=/home/administrator/backups/finnspark
DB=/home/administrator/finnspark/backend/finnspark.db
KEEP=14

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$BACKUP_DIR/finnspark-${STAMP}.db"

python3 - "$DB" "$OUT" <<'PY'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
dst_con = sqlite3.connect(dst)
src_con.backup(dst_con)   # online backup: consistent snapshot, no locks
dst_con.close()
src_con.close()
PY

# integrity check — a corrupt backup is worse than no backup
python3 - "$OUT" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
con.close()
sys.exit(0 if ok else 1)
PY
if [ $? -ne 0 ]; then
    echo "$(date -Is) INTEGRITY CHECK FAILED for $OUT — removing" >&2
    rm -f "$OUT"
    exit 1
fi

# Keep only the newest $KEEP dumps
ls -1t "$BACKUP_DIR"/finnspark-*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f
ls -1t "$BACKUP_DIR"/uploads-*.tar.gz 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm -f || true

# uploaded founder documents live outside the DB — snapshot them alongside
UPLOADS=/home/administrator/finnspark/backend/media/uploads
if [ -d "$UPLOADS" ]; then
    tar -czf "$BACKUP_DIR/uploads-${STAMP}.tar.gz" -C "$UPLOADS" . 2>/dev/null
fi

echo "$(date -Is) wrote $OUT ($(du -h "$OUT" | cut -f1)) — integrity ok"
