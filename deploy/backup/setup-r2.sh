#!/usr/bin/env bash
# One-time setup of the off-site backup repository (Cloudflare R2 + restic). Interactive:
#   ssh -t apps-1 sudo /opt/apps/daily-planner/deploy/backup/setup-r2.sh
# Asks for the R2 credentials (not echoed), generates the restic encryption password, stores
# everything in $RESTIC_ENV (root-only) and initialises the repository.
set -euo pipefail

RESTIC_ENV=${RESTIC_ENV:-/etc/restic/daily-planner.env}
[[ $EUID -eq 0 ]] || { echo "Run with sudo." >&2; exit 1; }
command -v restic >/dev/null || { echo "Install restic first: apt install restic" >&2; exit 1; }

read -rp  "R2 endpoint (https://<account-id>.r2.cloudflarestorage.com): " endpoint
read -rp  "Bucket name [apps-1-backups]: " bucket; bucket=${bucket:-apps-1-backups}
read -rp  "Access Key ID: " key_id
read -rsp "Secret Access Key (hidden): " secret; echo
endpoint=${endpoint%/}

password=""
if [[ -f $RESTIC_ENV ]] && grep -q '^RESTIC_PASSWORD=' "$RESTIC_ENV"; then
  password=$(grep '^RESTIC_PASSWORD=' "$RESTIC_ENV" | cut -d= -f2-)   # keep the existing one
fi
[[ -n $password ]] || password=$(openssl rand -base64 36 | tr -d '/+=' | head -c 40)

install -d -m 700 "$(dirname "$RESTIC_ENV")"
umask 077
cat > "$RESTIC_ENV" <<CONF
# restic → Cloudflare R2 for daily-planner backups. Root-only; never copy into git.
RESTIC_REPOSITORY=s3:$endpoint/$bucket/daily-planner
RESTIC_PASSWORD=$password
AWS_ACCESS_KEY_ID=$key_id
AWS_SECRET_ACCESS_KEY=$secret
AWS_DEFAULT_REGION=auto
CONF

set -a  # export everything the credentials file defines

# shellcheck source=/dev/null  # (the file exists only on the server)

source "$RESTIC_ENV"

set +a
if restic cat config >/dev/null 2>&1; then
  echo "Repository already initialised: credentials updated."
else
  restic init
fi

cat <<MSG

================================================================================
 Restic encryption password — SAVE IT NOW in your password manager:

     $password

 Without it the backups in R2 can never be decrypted (e.g. if this server is lost).
================================================================================
MSG
