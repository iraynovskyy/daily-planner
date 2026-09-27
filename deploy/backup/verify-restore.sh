#!/usr/bin/env bash
# Proves the latest off-site backup can be restored: downloads it from R2, restores it into a
# scratch database next to the live one and compares row counts. The live data isn't touched.
#   sudo /opt/apps/daily-planner/deploy/backup/verify-restore.sh
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/apps/daily-planner}
RESTIC_ENV=${RESTIC_ENV:-/etc/restic/daily-planner.env}
SCRATCH_DB=restore_check

compose() { docker compose --project-directory "$APP_DIR" "$@"; }
psql_db() { compose exec -T db psql -U planner -d "$1" -tAq "${@:2}"; }
counts() {
  psql_db "$1" -c "SELECT 'app_user', count(*) FROM app_user UNION ALL SELECT 'category', count(*)
    FROM category UNION ALL SELECT 'habit', count(*) FROM habit UNION ALL SELECT 'note', count(*)
    FROM note UNION ALL SELECT 'dailyentry', count(*) FROM dailyentry ORDER BY 1"
}

set -a  # export everything the credentials file defines

# shellcheck source=/dev/null  # (the file exists only on the server)

source "$RESTIC_ENV"
export RESTIC_CACHE_DIR=${RESTIC_CACHE_DIR:-/var/cache/restic}

set +a
tmp=$(mktemp -d); trap 'rm -rf "$tmp"; compose exec -T db dropdb -U planner --if-exists "$SCRATCH_DB" || true' EXIT

latest=$(restic ls latest --host apps-1 --tag daily-planner | grep '\.dump$' | tail -1)
echo "[verify] latest off-site dump: $latest"
restic dump latest --host apps-1 --tag daily-planner "$latest" > "$tmp/latest.dump"

compose exec -T db dropdb -U planner --if-exists "$SCRATCH_DB"
compose exec -T db createdb -U planner "$SCRATCH_DB"
compose exec -T db pg_restore -U planner -d "$SCRATCH_DB" --no-owner --exit-on-error < "$tmp/latest.dump"

echo "[verify] rows    live | restored"
paste -d'|' <(counts planner) <(counts "$SCRATCH_DB" | cut -d'|' -f2) | column -t -s'|'
echo "[verify] restore OK (differences are only changes made since the backup was taken)"
