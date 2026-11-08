#!/usr/bin/env bash
# Deploys ALLSAFE and PhishCatch to the home server's ~/stacks.
#
# Triggers:
#   push      .github/workflows/deploy-server.yml, on every push to ALLSAFE develop (self-hosted runner)
#   schedule  cron every 10 minutes, from the snapshot of the last deployed ALLSAFE tree
#             (~/stacks/.source/allsafe), to pick up new PhishCatch develop commits
#   manual    anyone running this script by hand
#
# PhishCatch follows its develop branch, but only commits whose Backend CI passed. Each stack has a
# content key built from exactly the files its images and configuration come from; a stack is
# rebuilt and restarted only when its key changes. Secrets stay in ~/stacks/<stack>/.env and are
# never read or printed here. A failure after the stacks start changing restores the previous
# images, stack files, models and ALLSAFE database.
set -Eeuo pipefail

SRC=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
STACKS=${ALLSAFE_STACKS_DIR:-$HOME/stacks}
REPO=${GH_REPOSITORY:-KeremDuz/ALLSAFE}
TRIGGER=${DEPLOY_TRIGGER:-manual}
FORCE=${DEPLOY_FORCE:-0}
PHISHCATCH_GIT=https://github.com/KeremDuz/PhishCatch.git
PHISHCATCH_API=https://api.github.com/repos/KeremDuz/PhishCatch
PHISHCATCH_BRANCH=develop
# Flutter web clients are not built on the server; these pinned images provide them.
HOME_CLIENT_IMAGE=${HOME_CLIENT_IMAGE:-allsafe-home-client:20261021}
PUBLIC_CLIENT_IMAGE=${PUBLIC_CLIENT_IMAGE:-phishcatch-public-client:20261021}
KEEP_IMAGES=3
KEEP_BACKUPS=10
WAIT_SECONDS=480
SNAPSHOT="$STACKS/.source/allsafe"
CACHE="$STACKS/.cache"
FAILED="$STACKS/.failed-releases"

log() { printf '%s [deploy:%s] %s\n' "$(date -u +%H:%M:%S)" "$TRIGGER" "$*"; }
# Best-effort phone notification (notify.sh); the same alert is not repeated.
alert_once() {
  local subject=$1 title=$2 message=$3
  [[ $(cat "$CACHE/last-alert" 2>/dev/null) == "$subject" ]] && return 0
  printf '%s
' "$subject" >"$CACHE/last-alert"
  bash "$SRC/deploy/server/notify.sh" "$title" "$message" high >/dev/null 2>&1 || true
}
LAST_ERROR=
ROLLBACK_ARMED=0
# Returns non-zero so that, once the ERR trap is armed, a failed check also rolls back.
die() {
  start_log
  log "ERROR: $*"
  LAST_ERROR=$*
  # Before anything changed nothing is rolled back, so alert here; otherwise rollback alerts.
  ((ROLLBACK_ARMED)) || alert_once "error-$TRIGGER-$*" "Dağıtım başarısız" "$* (tetikleyen: $TRIGGER; ayrıntı: ~/stacks/deploy.log)"
  return 1
}
LOG_STARTED=0
start_log() {
  ((LOG_STARTED)) && return 0
  LOG_STARTED=1
  exec > >(tee -a "$STACKS/deploy.log") 2>&1
}
# Scheduled runs stay silent unless something happens; a repeated notice is logged once.
notice_once() {
  local subject=$1
  shift
  if [[ $TRIGGER != schedule || $(cat "$CACHE/last-notice" 2>/dev/null) != "$subject" ]]; then
    start_log
    log "$*"
    printf '%s\n' "$subject" >"$CACHE/last-notice"
  fi
}

mkdir -p "$STACKS/backups" "$CACHE"
exec 9>"$STACKS/.deploy.lock"
if [[ $TRIGGER == schedule ]]; then
  flock -n 9 || exit 0
else
  flock -w 1800 9 || die "another deploy is still running after 30 minutes"
fi
[[ $TRIGGER == schedule ]] || start_log

compose() {
  local stack=$1
  shift
  docker compose --project-directory "$STACKS/$stack" -f "$STACKS/$stack/compose.yaml" \
    --env-file "$STACKS/$stack/.env" --env-file "$STACKS/$stack/release.env" "$@"
}
release_value() { sed -n "s/^$2=//p" "$STACKS/$1/release.env" 2>/dev/null | head -n 1; }
sha256() { sha256sum "$1" | cut -d' ' -f1; }
# Stable hash of the given files or directories under SRC plus extra words (no git needed).
content_key() {
  local extra=$1
  shift
  {
    printf '%s\n' "$extra"
    (
      cd "$SRC"
      for path in "$@"; do
        if [[ -e $path ]]; then
          find "$path" -type f ! -path '*/node_modules/*' ! -path '*/dist/*' ! -path '*/__pycache__/*' \
            -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum
        else
          printf 'missing %s\n' "$path"
        fi
      done
    )
  } | sha256sum | cut -c1-12
}
phishcatch_ci() {
  local json
  json=$(curl -fsS --max-time 20 -H 'Accept: application/vnd.github+json' \
    "$PHISHCATCH_API/commits/$1/check-runs?check_name=backend") || { echo unknown; return 0; }
  jq -r '.check_runs | if length == 0 then "missing" else (max_by(.id) |
    if .status != "completed" then "pending" elif .conclusion == "success" then "success"
    else "failure" end) end' <<<"$json"
}
failed_before() { grep -qxF "$1 $2" "$FAILED" 2>/dev/null; }

for stack in phishcatch allsafe; do
  [[ -f $STACKS/$stack/.env && -f $STACKS/$stack/release.env ]] ||
    die "$STACKS/$stack/.env or release.env is missing; see deploy/server/README.md"
done
COMMIT=$(git -C "$SRC" rev-parse HEAD 2>/dev/null || cat "$SRC/.commit" 2>/dev/null || echo unknown)

# ---------------------------------------------------------------- PhishCatch source
PC_REPO="$CACHE/phishcatch"
[[ -d $PC_REPO/.git ]] || git clone --quiet --no-checkout "$PHISHCATCH_GIT" "$PC_REPO"
git -C "$PC_REPO" fetch --quiet --prune origin \
  "+refs/heads/$PHISHCATCH_BRANCH:refs/remotes/origin/$PHISHCATCH_BRANCH"
PC_TIP=$(git -C "$PC_REPO" rev-parse "refs/remotes/origin/$PHISHCATCH_BRANCH")
PC_DEPLOYED=$(release_value phishcatch PHISHCATCH_COMMIT)
PC_COMMIT=$PC_TIP
if [[ $PC_TIP != "$PC_DEPLOYED" ]]; then
  ci=$(phishcatch_ci "$PC_TIP")
  if [[ $ci != success ]]; then
    [[ -n $PC_DEPLOYED ]] || die "PhishCatch ${PC_TIP:0:8} Backend CI is $ci and no deployed commit is recorded"
    notice_once "ci-$PC_TIP-$ci" "PhishCatch ${PC_TIP:0:8} Backend CI is $ci; keeping ${PC_DEPLOYED:0:8}"
    PC_COMMIT=$PC_DEPLOYED
  fi
fi
git -C "$PC_REPO" cat-file -e "$PC_COMMIT^{commit}" 2>/dev/null || git -C "$PC_REPO" fetch --quiet origin "$PC_COMMIT"

# ---------------------------------------------------------------- what changed
ALLSAFE_KEY=$(content_key "$HOME_CLIENT_IMAGE" .dockerignore apps/api/Dockerfile apps/api/pyproject.toml \
  apps/api/requirements.lock apps/api/src apps/api/alembic.ini apps/api/alembic apps/web \
  deploy/home/nginx.conf deploy/server/allsafe-edge.Dockerfile deploy/server/stacks/allsafe)
PHISHCATCH_KEY=$(content_key "$PUBLIC_CLIENT_IMAGE $(git -C "$PC_REPO" rev-parse "$PC_COMMIT:apps/backend")" \
  deploy/public/nginx.conf deploy/server/public-edge.Dockerfile deploy/server/stacks/phishcatch \
  deploy/server/models.lock)
CUR_ALLSAFE=$(release_value allsafe RELEASE)
CUR_PHISHCATCH=$(release_value phishcatch RELEASE)
DO_ALLSAFE=0
DO_PHISHCATCH=0
[[ $ALLSAFE_KEY != "$CUR_ALLSAFE" || $FORCE == 1 ]] && DO_ALLSAFE=1
[[ $PHISHCATCH_KEY != "$CUR_PHISHCATCH" || $FORCE == 1 ]] && DO_PHISHCATCH=1
# Scheduled runs never retry a release that already failed and was rolled back.
if [[ $TRIGGER == schedule ]]; then
  if ((DO_ALLSAFE)) && failed_before allsafe "$ALLSAFE_KEY"; then
    DO_ALLSAFE=0
    notice_once "failed-allsafe-$ALLSAFE_KEY" "allsafe $ALLSAFE_KEY failed before; not retrying"
  fi
  if ((DO_PHISHCATCH)) && failed_before phishcatch "$PHISHCATCH_KEY"; then
    DO_PHISHCATCH=0
    notice_once "failed-phishcatch-$PHISHCATCH_KEY" "phishcatch $PHISHCATCH_KEY failed before; not retrying"
  fi
fi

snapshot_source() {
  # Keep the deployed ALLSAFE tree for scheduled runs; skipped when running from the snapshot.
  git -C "$SRC" rev-parse HEAD >/dev/null 2>&1 || return 0
  rm -rf "$SNAPSHOT.new" "$SNAPSHOT.old"
  mkdir -p "$SNAPSHOT.new"
  git -C "$SRC" archive HEAD | tar -x -C "$SNAPSHOT.new"
  printf '%s\n' "$COMMIT" >"$SNAPSHOT.new/.commit"
  if [[ -d $SNAPSHOT ]]; then mv "$SNAPSHOT" "$SNAPSHOT.old"; fi
  mv "$SNAPSHOT.new" "$SNAPSHOT"
  rm -rf "$SNAPSHOT.old"
}

if ((DO_ALLSAFE == 0 && DO_PHISHCATCH == 0)); then
  if [[ $PC_COMMIT != "$PC_DEPLOYED" && $PHISHCATCH_KEY == "$CUR_PHISHCATCH" ]]; then
    # New PhishCatch commit without backend changes: nothing to restart, just record it.
    sed -i "/^PHISHCATCH_COMMIT=/d" "$STACKS/phishcatch/release.env"
    printf 'PHISHCATCH_COMMIT=%s\n' "$PC_COMMIT" >>"$STACKS/phishcatch/release.env"
  fi
  [[ $TRIGGER == schedule ]] || log "up to date (allsafe $CUR_ALLSAFE, phishcatch $CUR_PHISHCATCH)"
  snapshot_source
  exit 0
fi

start_log
BACKUP="$STACKS/backups/deploy-$(date -u +%Y%m%dT%H%M%SZ)-${COMMIT:0:12}"
mkdir -p "$BACKUP"
chmod 700 "$BACKUP"
log "ALLSAFE ${COMMIT:0:12}, PhishCatch ${PC_COMMIT:0:12}; backup $BACKUP"
((DO_PHISHCATCH)) && log "phishcatch $CUR_PHISHCATCH -> $PHISHCATCH_KEY"
((DO_ALLSAFE)) && log "allsafe $CUR_ALLSAFE -> $ALLSAFE_KEY"

# ---------------------------------------------------------------- build (nothing live changes yet)
build() {
  local tag=$1
  shift
  log "build $tag"
  docker build --quiet --tag "$tag" "$@" >/dev/null
}
if ((DO_PHISHCATCH)); then
  git -C "$PC_REPO" -c advice.detachedHead=false checkout --quiet --force --detach "$PC_COMMIT"
  build "phishcatch-backend:$PHISHCATCH_KEY" "$PC_REPO/apps/backend"
  build "phishcatch-public-edge:$PHISHCATCH_KEY" -f "$SRC/deploy/server/public-edge.Dockerfile" \
    --build-arg "CLIENT=$PUBLIC_CLIENT_IMAGE" "$SRC"
fi
if ((DO_ALLSAFE)); then
  build "allsafe-api:$ALLSAFE_KEY" -f "$SRC/apps/api/Dockerfile" "$SRC"
  build "allsafe-edge:$ALLSAFE_KEY" -f "$SRC/deploy/server/allsafe-edge.Dockerfile" \
    --build-arg "CLIENT=$HOME_CLIENT_IMAGE" "$SRC"
fi

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
if ((DO_PHISHCATCH)); then
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
  ((MODELS_CHANGED)) || rm -rf "$STAGED_MODELS"
fi

# ---------------------------------------------------------------- database backups
backup_sqlite() {
  local container=$1 path=$2 out=$3
  if [[ $(docker inspect -f '{{.State.Running}}' "$container" 2>/dev/null) != true ]]; then
    log "warning: $container is not running; no backup of $path"
    return 0
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
((DO_ALLSAFE)) && backup_sqlite allsafe-api-1 /app/data/allsafe.db "$BACKUP/allsafe.db"
((DO_PHISHCATCH)) && backup_sqlite phishcatch-backend-1 /app/data/phishcatch_training.sqlite3 \
  "$BACKUP/phishcatch_training.sqlite3"

# ---------------------------------------------------------------- apply with rollback
CHANGED_PHISHCATCH=0
CHANGED_ALLSAFE=0
MODELS_SWAPPED=0
save_stack() {
  mkdir -p "$BACKUP/$1"
  cp -p "$STACKS/$1"/compose.yaml "$STACKS/$1"/*.conf "$STACKS/$1"/release.env "$BACKUP/$1"/
}
apply_stack() {
  local stack=$1 key=$2
  shift 2
  cp "$SRC/deploy/server/stacks/$stack"/* "$STACKS/$stack"/
  printf 'RELEASE=%s\nCOMMIT=%s\n' "$key" "$COMMIT" >"$STACKS/$stack/release.env"
  if [[ $stack == phishcatch ]]; then
    printf 'PHISHCATCH_COMMIT=%s\n' "$PC_COMMIT" >>"$STACKS/$stack/release.env"
  fi
  log "start $stack $key"
  compose "$stack" up -d --remove-orphans --wait --wait-timeout "$WAIT_SECONDS" "$@"
}
restore_stack() {
  cp -p "$BACKUP/$1"/* "$STACKS/$1"/
  log "rollback $1 to $(release_value "$1" RELEASE)"
}
rollback() {
  local status=$?
  trap - ERR
  set +e
  log "deploy failed (exit $status); rolling back"
  ((CHANGED_ALLSAFE)) && printf 'allsafe %s\n' "$ALLSAFE_KEY" >>"$FAILED"
  ((CHANGED_PHISHCATCH)) && printf 'phishcatch %s\n' "$PHISHCATCH_KEY" >>"$FAILED"
  if ((CHANGED_ALLSAFE)); then
    restore_stack allsafe
    compose allsafe stop api phishcatch_link edge
    if [[ -f $BACKUP/allsafe.db ]]; then
      # Migrations may have run; bring back the matching pre-deploy database.
      docker run --rm --user 0 --entrypoint sh -v allsafe_api-data:/data -v "$BACKUP:/backup:ro" \
        "allsafe-api:$CUR_ALLSAFE" -c 'cp /backup/allsafe.db /data/allsafe.db &&
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
  log "rollback finished; the failed release is not live"
  alert_once "rollback-$ALLSAFE_KEY-$PHISHCATCH_KEY" "Dağıtım geri alındı"     "Yeni sürüm kontrolü geçemedi, önceki sürüm geri yüklendi. ${LAST_ERROR:-exit $status} (allsafe $ALLSAFE_KEY, phishcatch $PHISHCATCH_KEY; ayrıntı: ~/stacks/deploy.log)"
  exit "$status"
}
trap rollback ERR
ROLLBACK_ARMED=1

save_stack phishcatch
save_stack allsafe
if ((DO_PHISHCATCH)); then
  CHANGED_PHISHCATCH=1
  if ((MODELS_CHANGED)); then
    mv "$MODELS" "$BACKUP/models" && mv "$STAGED_MODELS" "$MODELS"
    MODELS_SWAPPED=1
    apply_stack phishcatch "$PHISHCATCH_KEY" --force-recreate
  else
    apply_stack phishcatch "$PHISHCATCH_KEY"
  fi
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:18190/api/v1/integrations/allsafe/health)
  [[ $code == 401 ]] || die "integration edge answered $code without a key (expected 401)"
  curl -fsS --max-time 15 -o /dev/null http://127.0.0.1:18181/ || die "public edge is not answering"
fi
if ((DO_ALLSAFE)); then
  CHANGED_ALLSAFE=1
  apply_stack allsafe "$ALLSAFE_KEY"
  curl -fsS --max-time 15 -o /dev/null http://127.0.0.1:18180/health/ready || die "allsafe edge is not ready"
fi
for attempt in 1 2 3 4 5 6; do
  docker exec allsafe-api-1 python -c 'import json, os, urllib.request
request = urllib.request.Request("http://127.0.0.1:9000/api/v1/integrations/allsafe/health",
    headers={"X-Integration-Key": os.environ["ALLSAFE_PHISHCATCH_INTEGRATION_KEY"]})
body = json.load(urllib.request.urlopen(request, timeout=15))
assert body["status"] == "ok" and body["url_model_available"] and body["html_model_available"], body' \
    >/dev/null 2>&1 && break
  ((attempt < 6)) || die "ALLSAFE cannot reach a healthy PhishCatch"
  sleep 10
done
trap - ERR
log "live: allsafe $(release_value allsafe RELEASE), phishcatch $(release_value phishcatch RELEASE)"
changed=()
((DO_ALLSAFE)) && changed+=("ALLSAFE ${COMMIT:0:7}")
((DO_PHISHCATCH)) && changed+=("PhishCatch ${PC_COMMIT:0:7}")
rm -f "$CACHE/last-alert"
bash "$SRC/deploy/server/notify.sh" "Güncellendi" "${changed[*]} canlıda (tetikleyen: $TRIGGER)." default >/dev/null 2>&1 || true
snapshot_source

# ---------------------------------------------------------------- cleanup (best effort)
set +e
prune_images() {
  local keep_a=$1 keep_b=$2 repository tag
  shift 2
  for repository in "$@"; do
    docker image ls "$repository" --format '{{.Tag}}' | grep -vxF -e "$keep_a" -e "$keep_b" |
      tail -n +"$KEEP_IMAGES" | while read -r tag; do docker image rm "$repository:$tag" >/dev/null; done
  done
}
prune_images "$(release_value allsafe RELEASE)" "$CUR_ALLSAFE" allsafe-api allsafe-edge
prune_images "$(release_value phishcatch RELEASE)" "$CUR_PHISHCATCH" phishcatch-backend phishcatch-public-edge
ls -1dt "$STACKS"/backups/deploy-* 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | while read -r old; do rm -rf "$old"; done
rm -rf "$MODELS.failed"
docker builder prune -f --filter until=168h >/dev/null
exit 0
