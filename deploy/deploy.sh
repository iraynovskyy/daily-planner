#!/usr/bin/env bash
# Deploys one app image on the server, with a pre-deploy backup and automatic rollback.
#
# Called by GitHub Actions over SSH with a key that is locked to this script (a "forced
# command" in ~/.ssh/authorized_keys), so the image reference arrives in $SSH_ORIGINAL_COMMAND:
#   ssh ops@server ghcr.io/<owner>/daily-planner:sha-<commit>
# By hand:  deploy/deploy.sh ghcr.io/<owner>/daily-planner:sha-<commit>
set -euo pipefail

APP_DIR=${APP_DIR:-/opt/apps/daily-planner}
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-90}

image=${SSH_ORIGINAL_COMMAND:-${1:-}}
# Only an image reference of this exact shape is accepted — nothing else can be run through here.
if [[ ! $image =~ ^ghcr\.io/[a-z0-9._-]+/[a-z0-9._-]+:sha-[0-9a-f]{7,40}$ ]]; then
  echo "refusing: not an image reference: ${image:-<empty>}" >&2
  exit 2
fi

cd "$APP_DIR"
compose() { docker compose "$@"; }
log() { echo "[deploy] $*"; }

set_image() {  # records the image in .env so manual `docker compose up` keeps using it
  if grep -q '^APP_IMAGE=' .env; then
    sed -i "s|^APP_IMAGE=.*|APP_IMAGE=$1|" .env
  else
    echo "APP_IMAGE=$1" >> .env
  fi
}

wait_healthy() {
  local id deadline=$((SECONDS + HEALTH_TIMEOUT))
  id=$(compose ps -q app)
  while ((SECONDS < deadline)); do
    [[ $(docker inspect -f '{{.State.Health.Status}}' "$id" 2>/dev/null) == healthy ]] && return 0
    sleep 3
  done
  return 1
}

previous=$(grep '^APP_IMAGE=' .env | cut -d= -f2- || true)
log "deploying $image (previous: ${previous:-none})"

# Compose file and ops scripts come from git; the app itself comes from the image.
git pull --quiet --ff-only

log "pre-deploy backup"
sudo systemctl start daily-planner-backup.service

docker pull --quiet "$image" >/dev/null
set_image "$image"
compose up -d --no-build app

if wait_healthy; then
  log "healthy: $image"
  docker image prune -f --filter "until=168h" >/dev/null  # drop images unused for a week
  exit 0
fi

log "NOT healthy after ${HEALTH_TIMEOUT}s; last logs:"
compose logs --tail 30 app || true
if [[ -n $previous ]]; then
  log "rolling back to $previous"
  set_image "$previous"
  compose up -d --no-build app
  if wait_healthy; then log "rollback healthy"; else log "rollback ALSO unhealthy — needs a look"; fi
fi
exit 1
