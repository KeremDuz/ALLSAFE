#!/usr/bin/env bash
# Weekly backup of the home server's own state, run by cron (# ALLSAFE_BACKUP).
#
# Writes ~/stacks/backups/weekly/allsafe-backup-<UTC time>.tar (mode 600), points
# allsafe-backup-latest.tar at it and keeps the newest 6. A copy is pulled off the server by
# scripts/pull-server-backup.ps1 on the owner's PC. The archive holds the stacks' .env files, so
# it contains secrets: keep every copy private.
#
# Included: ALLSAFE and PhishCatch databases (consistent SQLite backups), stack configuration and
# secrets, downloads (APK), Wazuh manager configuration (agent keys, enrollment password, API
# users) and Portainer data. Not included: Wazuh alert history (Indexer data), which is large,
# and PhishCatch models, which live in a private GitHub release.
set -Eeuo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STACKS=${ALLSAFE_STACKS_DIR:-$HOME/stacks}
OUT="$STACKS/backups/weekly"
KEEP=6
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TOOL_IMAGE=nginx:stable-alpine # already on the server; provides tar for volume copies
umask 077
mkdir -p "$OUT"
WORK=$(mktemp -d "$STACKS/backups/.weekly-XXXXXX")
trap 'rm -rf "$WORK"' EXIT
log() { printf '%s [backup] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"$STACKS/backup.log"; }
fail() {
  log "ERROR: $*"
  bash "$HERE/notify.sh" "Haftalık yedek alınamadı" "$*" high || true
  exit 1
}
trap 'fail "unexpected error on line $LINENO"' ERR

sqlite_backup() {
  local container=$1 path=$2 out=$3
  [[ $(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null) == true ]] ||
    fail "$container is not running; no backup of $path"
  docker exec "$container" python -c 'import sqlite3,sys
s = sqlite3.connect(sys.argv[1]); d = sqlite3.connect(sys.argv[2]); s.backup(d); d.close()' \
    "$path" "$path.weekly"
  docker cp -q "$container:$path.weekly" "$out"
  docker exec "$container" rm -f "$path.weekly"
  [[ $(python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("pragma integrity_check").fetchone()[0])' "$out") == ok ]] ||
    fail "$(basename "$out") failed the integrity check"
}
archive_volume() {
  local volume=$1 name=$2
  docker run --rm --network none -v "$volume:/src:ro" -v "$WORK:/out" --entrypoint sh "$TOOL_IMAGE" \
    -c "tar -czf /out/$name -C /src . && chown $(id -u):$(id -g) /out/$name && chmod 600 /out/$name"
}

sqlite_backup allsafe-api-1 /app/data/allsafe.db "$WORK/allsafe.db"
sqlite_backup phishcatch-backend-1 /app/data/phishcatch_training.sqlite3 "$WORK/phishcatch_training.sqlite3"
archive_volume wazuh_wazuh_etc wazuh-etc.tar.gz
archive_volume wazuh_wazuh_api_configuration wazuh-api-configuration.tar.gz
archive_volume portainer_portainer-data portainer-data.tar.gz
# Stack definitions, secrets and downloads; the Wazuh certificate folder is root-only and can be
# regenerated with the wazuh stack's generate-indexer-certs.yml.
tar -czf "$WORK/stacks.tar.gz" -C "$STACKS" \
  --exclude='./backups' --exclude='./.cache' --exclude='./.source' --exclude='./wazuh-docker-src' \
  --exclude='./phishcatch/models' --exclude='./phishcatch/models.*' \
  --exclude='./wazuh/config/wazuh_indexer_ssl_certs' --exclude='*.log' --exclude='*.lock' .
printf 'created=%s\nhost=%s\nallsafe=%s\nphishcatch=%s\n' "$STAMP" "$(hostname)" \
  "$(sed -n 's/^COMMIT=//p' "$STACKS/allsafe/release.env")" \
  "$(sed -n 's/^PHISHCATCH_COMMIT=//p' "$STACKS/phishcatch/release.env")" >"$WORK/MANIFEST"
(cd "$WORK" && sha256sum -- * >SHA256SUMS)

archive="$OUT/allsafe-backup-$STAMP.tar"
tar -cf "$archive.part" -C "$WORK" .
mv "$archive.part" "$archive"
ln -sfn "$(basename "$archive")" "$OUT/allsafe-backup-latest.tar"
ls -1t "$OUT"/allsafe-backup-2*.tar 2>/dev/null | tail -n +$((KEEP + 1)) | while read -r old; do rm -f "$old"; done
log "ok $(basename "$archive") $(du -h "$archive" | cut -f1)"
