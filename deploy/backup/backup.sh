#!/usr/bin/env bash
# Nightly backup of the daily-planner PostgreSQL database (run as root by the systemd timer).
#   1. pg_dump (custom format) into $LOCAL_DIR, keeping the last $KEEP_LOCAL_DAYS days
#   2. an encrypted, deduplicated off-site copy with restic (Cloudflare R2, S3 API)
#   3. restic retention (daily / weekly / monthly) and an integrity check
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/apps/daily-planner}
LOCAL_DIR=${LOCAL_DIR:-/var/backups/daily-planner}
KEEP_LOCAL_DAYS=${KEEP_LOCAL_DAYS:-14}
RESTIC_ENV=${RESTIC_ENV:-/etc/restic/daily-planner.env}

compose() { docker compose --project-directory "$APP_DIR" "$@"; }
log() { echo "[backup] $*"; }

umask 077
mkdir -p "$LOCAL_DIR"
dump="$LOCAL_DIR/planner_$(date +%Y-%m-%d_%H%M).dump"

log "dumping database → $dump"
compose exec -T db pg_dump -U planner -d planner --format=custom --no-owner > "$dump.partial"
# A dump that pg_restore can't read, or that lacks the main tables, is not a backup.
compose exec -T db pg_restore --list < "$dump.partial" | grep -q "TABLE DATA public dailyentry"
mv "$dump.partial" "$dump"
log "dump ok ($(du -h "$dump" | cut -f1))"

find "$LOCAL_DIR" -name 'planner_*.dump' -mtime +"$KEEP_LOCAL_DAYS" -delete

if [[ ! -f $RESTIC_ENV ]]; then
  log "no $RESTIC_ENV: off-site copy skipped (run setup-r2.sh)"
  exit 0
fi
set -a  # export everything the credentials file defines
# shellcheck source=/dev/null  # (the file exists only on the server)
source "$RESTIC_ENV"
set +a

log "uploading to $RESTIC_REPOSITORY"
restic backup --quiet --host apps-1 --tag daily-planner "$dump"
restic forget --quiet --host apps-1 --tag daily-planner \
  --keep-daily 30 --keep-weekly 12 --keep-monthly 24 --prune
restic check --quiet
log "off-site copy ok; latest snapshots:"
restic snapshots --host apps-1 --tag daily-planner --latest 3 --compact
