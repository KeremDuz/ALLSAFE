#!/usr/bin/env bash
# Deploys this checkout to the home server's phishcatch and allsafe stacks.
#
# Run by .github/workflows/deploy-server.yml on the server's self-hosted runner, or by
# hand from a checkout with the PhishCatch submodule. Secrets stay in ~/stacks/<stack>/.env;
# nothing here reads or prints them. On any failure after the stacks start changing, the
# previous images, stack files, models and (for ALLSAFE) database are restored.
set -Eeuo pipefail

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
STACKS=${ALLSAFE_STACKS_DIR:-$HOME/stacks}
REPO=${GH_REPOSITORY:-KeremDuz/ALLSAFE}
RELEASE=${DEPLOY_RELEASE:-$(git -C "$SRC" rev-parse --short=12 HEAD)}
# Flutter web clients are not built on the server; these pinned images provide them.
HOME_CLIENT_IMAGE=${HOME_CLIENT_IMAGE:-allsafe-home-client:20261021}
PUBLIC_CLIENT_IMAGE=${PUBLIC_CLIENT_IMAGE:-phishcatch-public-client:20261021}
KEEP_IMAGES=3
KEEP_BACKUPS=10
WAIT_SECONDS=480

log() { printf '%s [deploy] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
# Returns non-zero so that, once the ERR trap is armed, a failed check also rolls back.
die() {
  log "ERROR: $*"
  return 1
}

[[ $RELEASE =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid release id"
mkdir -p "$STACKS/backups"
exec 9>"$STACKS/.deploy.lock"
flock -n 9 || die "another deploy is running"
exec > >(tee -a "$STACKS/deploy.log") 2>&1

compose() {
  local stack=$1
  shift
  docker compose --project-directory "$STACKS/$stack" -f "$STACKS/$stack/compose.yaml" \
    --env-file "$STACKS/$stack/.env" --env-file "$STACKS/$stack/release.env" "$@"
}
current_release() { sed -n 's/^RELEASE=//p' "$STACKS/$1/release.env" 2>/dev/null; }
sha256() { sha256sum "$1" | cut -d' ' -f1; }

for stack in phishcatch allsafe; do
  [[ -f $STACKS/$stack/.env ]] || die "$STACKS/$stack/.env is missing"
done
[[ -f $SRC/packages/phishcatch/apps/backend/Dockerfile ]] || die "PhishCatch submodule is not checked out"
PREV_PHISHCATCH=$(current_release phishcatch)
PREV_ALLSAFE=$(current_release allsafe)
[[ -n $PREV_PHISHCATCH && -n $PREV_ALLSAFE ]] || die "release.env missing; see deploy/server/README.md (one-time setup)"
BACKUP="$STACKS/backups/deploy-$(date -u +%Y%m%dT%H%M%SZ)-$RELEASE"
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
log "release $RELEASE (was phishcatch $PREV_PHISHCATCH, allsafe $PREV_ALLSAFE), backup $BACKUP"

# ---------------------------------------------------------------- build (no changes yet)
build() {
  local tag=$1
  shift
  log "build $tag"
  docker build --quiet --tag "$tag" "$@" >/dev/null
}
build "phishcatch-backend:$RELEASE" "$SRC/packages/phishcatch/apps/backend"
build "phishcatch-public-edge:$RELEASE" -f "$SRC/deploy/server/public-edge.Dockerfile" \
  --build-arg "CLIENT=$PUBLIC_CLIENT_IMAGE" "$SRC"
build "allsafe-api:$RELEASE" -f "$SRC/apps/api/Dockerfile" "$SRC"
build "allsafe-edge:$RELEASE" -f "$SRC/deploy/server/allsafe-edge.Dockerfile" \
  --build-arg "CLIENT=$HOME_CLIENT_IMAGE" "$SRC"

# ---------------------------------------------------------------- models (staged, not live)
MODELS="$STACKS/phishcatch/models"
STAGED_MODELS="$STACKS/phishcatch/models.new"
MODELS_CHANGED=0
download_asset() {
  local tag=$1 name=$2 dest=$3 headers url
  [[ -n ${GH_TOKEN:-} ]] || die "GH_TOKEN is required to download $name"
  headers=$(mktemp)
  chmod 600 "$headers"
  printf 'Authorization: Bearer %s\n' "$GH_TOKEN" >"$headers"
  url=$(curl -fsSL -H @"$headers" -H 'Accept: application/vnd.github+json' \
    "https://api.github.com/repos/$REPO/releases/tags/$tag" |
    jq -r --arg name "$name" '.assets[] | select(.name == $name) | .url')
  if [[ -z $url ]]; then
    rm -f "$headers"
    die "release $tag has no asset $name"
  fi
  curl -fSL --retry 3 --silent --show-error -H @"$headers" -H 'Accept: application/octet-stream' \
    -o "$dest" "$url" || { rm -f "$headers"; die "download of $name failed"; }
  rm -f "$headers"
}
rm -rf "$STAGED_MODELS"
mkdir -p "$STAGED_MODELS"
cp -al "$MODELS"/. "$STAGED_MODELS"/ 2>/dev/null || true
while read -r file sha tag _; do
  [[ -z $file || $file == \#* ]] && continue
  [[ $file =~ ^[A-Za-z0-9._-]+$ && $sha =~ ^[0-9a-f]{64}$ ]] || die "invalid models.lock line for $file"
  if [[ -f $MODELS/$file && $(sha256 "$MODELS/$file") == "$sha" ]]; then
    continue
  fi
  log "model $file -> $tag"
  rm -f "$STAGED_MODELS/$file"
  download_asset "$tag" "$file" "$STAGED_MODELS/$file.part"
  # Pickled models execute code when loaded: never accept a file that does not match the lock.
  [[ $(sha256 "$STAGED_MODELS/$file.part") == "$sha" ]] || die "SHA-256 mismatch for $file"
  chmod 644 "$STAGED_MODELS/$file.part"
  mv "$STAGED_MODELS/$file.part" "$STAGED_MODELS/$file"
  MODELS_CHANGED=1
done <"$SRC/deploy/server/models.lock"
if ((MODELS_CHANGED == 0)); then rm -rf "$STAGED_MODELS"; fi

# ---------------------------------------------------------------- database backups
backup_sqlite() {
  local container=$1 path=$2 out=$3
  if [[ $(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null) != true ]]; then
    log "warning: $container is not running; no backup of $path"
    return
  fi
  docker exec "$container" python -c 'import sqlite3,sys
s = sqlite3.connect(sys.argv[1]); d = sqlite3.connect(sys.argv[2]); s.backup(d); d.close()' \
    "$path" "$path.predeploy"
  docker cp -q "$container:$path.predeploy" "$out"
  docker exec "$container" rm -f "$path.predeploy"
  [[ $(python3 -c 'import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute("pragma integrity_check").fetchone()[0])' "$out") == ok ]] ||
    die "backup $out failed the integrity check"
  log "backup $(basename "$out") ok"
}
backup_sqlite allsafe-api-1 /app/data/allsafe.db "$BACKUP/allsafe.db"
backup_sqlite phishcatch-backend-1 /app/data/phishcatch_training.sqlite3 "$BACKUP/phishcatch_training.sqlite3"

# ---------------------------------------------------------------- apply with rollback
CHANGED_PHISHCATCH=0
CHANGED_ALLSAFE=0
MODELS_SWAPPED=0

save_stack() {
  mkdir -p "$BACKUP/$1"
  cp -p "$STACKS/$1"/compose.yaml "$STACKS/$1"/*.conf "$STACKS/$1"/release.env "$BACKUP/$1"/
}
apply_stack() {
  local stack=$1
  shift
  cp "$SRC/deploy/server/stacks/$stack"/* "$STACKS/$stack"/
  printf 'RELEASE=%s\n' "$RELEASE" >"$STACKS/$stack/release.env"
  log "start $stack $RELEASE"
  compose "$stack" up -d --remove-orphans --wait --wait-timeout "$WAIT_SECONDS" "$@"
}
restore_stack() {
  local stack=$1
  cp -p "$BACKUP/$stack"/* "$STACKS/$stack"/
  log "rollback $stack to $(current_release "$stack")"
}

rollback() {
  local status=$?
  trap - ERR
  set +e
  log "deploy failed (exit $status); rolling back"
  if ((CHANGED_ALLSAFE)); then
    restore_stack allsafe
    compose allsafe stop api phishcatch_link edge
    if [[ -f $BACKUP/allsafe.db ]]; then
      # Migrations may have run; bring back the matching pre-deploy database.
      docker run --rm --user 0 --entrypoint sh -v allsafe_api-data:/data -v "$BACKUP:/backup:ro" \
        "allsafe-api:$PREV_ALLSAFE" -c 'cp /backup/allsafe.db /data/allsafe.db &&
        rm -f /data/allsafe.db-wal /data/allsafe.db-shm && chown 10001:10001 /data/allsafe.db'
      log "restored allsafe database"
    fi
  fi
  if ((MODELS_SWAPPED)); then
    rm -rf "$MODELS.failed"
    mv "$MODELS" "$MODELS.failed" && mv "$BACKUP/models" "$MODELS"
    log "restored previous models"
  fi
  if ((CHANGED_PHISHCATCH)); then
    restore_stack phishcatch
    compose phishcatch up -d --remove-orphans --force-recreate --wait --wait-timeout "$WAIT_SECONDS" ||
      log "ERROR: phishcatch did not become healthy after rollback"
  fi
  if ((CHANGED_ALLSAFE)); then
    compose allsafe up -d --remove-orphans --force-recreate --wait --wait-timeout "$WAIT_SECONDS" ||
      log "ERROR: allsafe did not become healthy after rollback"
  fi
  log "rollback finished; failed release $RELEASE is not live"
  exit "$status"
}
trap rollback ERR

save_stack phishcatch
save_stack allsafe

CHANGED_PHISHCATCH=1
if ((MODELS_CHANGED)); then
  mv "$MODELS" "$BACKUP/models" && mv "$STAGED_MODELS" "$MODELS"
  MODELS_SWAPPED=1
  apply_stack phishcatch --force-recreate
else
  apply_stack phishcatch
fi
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:18190/api/v1/integrations/allsafe/health)
[[ $code == 401 ]] || die "integration edge answered $code without a key (expected 401)"
curl -fsS --max-time 15 -o /dev/null http://127.0.0.1:18181/ || die "public edge is not answering"

CHANGED_ALLSAFE=1
apply_stack allsafe
curl -fsS --max-time 15 -o /dev/null http://127.0.0.1:18180/health/ready || die "allsafe edge is not ready"
docker exec allsafe-api-1 python -c 'import json, os, urllib.request
request = urllib.request.Request("http://127.0.0.1:9000/api/v1/integrations/allsafe/health",
    headers={"X-Integration-Key": os.environ["ALLSAFE_PHISHCATCH_INTEGRATION_KEY"]})
body = json.load(urllib.request.urlopen(request, timeout=15))
assert body["status"] == "ok" and body["url_model_available"] and body["html_model_available"], body' ||
  die "ALLSAFE cannot reach a healthy PhishCatch"
trap - ERR
log "release $RELEASE is live"

# ---------------------------------------------------------------- cleanup (best effort)
set +e
for repository in phishcatch-backend phishcatch-public-edge allsafe-api allsafe-edge; do
  docker image ls "$repository" --format '{{.Tag}}' | grep -vxF -e "$RELEASE" -e "$PREV_PHISHCATCH" -e "$PREV_ALLSAFE" |
    tail -n +"$KEEP_IMAGES" | while read -r tag; do docker image rm "$repository:$tag" >/dev/null; done
done
ls -1dt "$STACKS"/backups/deploy-* 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | while read -r old; do rm -rf "$old"; done
rm -rf "$MODELS.failed"
docker builder prune -f --filter until=168h >/dev/null
exit 0
