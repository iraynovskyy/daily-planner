#!/usr/bin/env bash
# Disaster recovery: replaces the LIVE database with a backup. Stops the app while restoring.
#   sudo ./restore.sh /var/backups/daily-planner/planner_2026-09-28_0330.dump   # a local dump
#   sudo ./restore.sh latest                                                    # newest in R2
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/apps/daily-planner}
RESTIC_ENV=${RESTIC_ENV:-/etc/restic/daily-planner.env}
compose() { docker compose --project-directory "$APP_DIR" "$@"; }

dump=${1:?usage: restore.sh <dump file | latest>}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
if [[ $dump == latest ]]; then
  set -a  # export everything the credentials file defines
  # shellcheck source=/dev/null  # (the file exists only on the server)
  source "$RESTIC_ENV"
  set +a
  path=$(restic ls latest --host apps-1 --tag daily-planner | grep '\.dump$' | tail -1)
  restic dump latest --host apps-1 --tag daily-planner "$path" > "$tmp/restore.dump"
  dump="$tmp/restore.dump"
fi
[[ -s $dump ]] || { echo "No such dump: $dump" >&2; exit 1; }

read -rp "This REPLACES all live data with $1. Type 'restore' to continue: " answer
[[ $answer == restore ]] || { echo "Cancelled."; exit 1; }

"$(dirname "$0")/backup.sh" || echo "(warning: safety backup of the current state failed)"
compose stop app
compose exec -T db pg_restore -U planner -d planner --clean --if-exists --no-owner \
  --exit-on-error < "$dump"
compose start app
echo "Restored from $1."
