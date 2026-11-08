#!/usr/bin/env bash
# Publishes trained PhishCatch model files as assets of a private GitHub release in this
# repository and pins them in deploy/server/models.lock. Run from any checkout (Git Bash
# on Windows works) with an authenticated GitHub CLI:
#
#   deploy/server/publish-model.sh phishcatch-models-20261201 path/to/phishcatch_url_model.pkl
#
# Then commit models.lock and merge it; the server deploy downloads and verifies the files.
set -euo pipefail

usage() { echo "usage: $0 <release-tag> <model-file>..." >&2; exit 2; }
(($# >= 2)) || usage
tag=$1
shift
[[ $tag =~ ^phishcatch-models-[0-9A-Za-z._-]+$ ]] || { echo "tag must start with phishcatch-models-" >&2; exit 2; }
root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
lock="$root/deploy/server/models.lock"
repo=$(gh repo view --json nameWithOwner -q .nameWithOwner)
[[ $(gh repo view "$repo" --json visibility -q .visibility) == PRIVATE ]] ||
  { echo "$repo is not private; refusing to publish models there" >&2; exit 1; }

for file in "$@"; do
  name=$(basename "$file")
  [[ -f $file && $name =~ ^[A-Za-z0-9._-]+$ ]] || { echo "bad model file: $file" >&2; exit 1; }
  grep -q "^$name " "$lock" || { echo "$name is not listed in models.lock" >&2; exit 1; }
done

if ! gh release view "$tag" --repo "$repo" >/dev/null 2>&1; then
  gh release create "$tag" --repo "$repo" --latest=false --title "$tag" \
    --notes "PhishCatch model files. Pinned by deploy/server/models.lock."
fi
for file in "$@"; do
  name=$(basename "$file")
  sha=$(sha256sum "$file" | cut -d' ' -f1)
  echo "upload $name ($sha)"
  gh release upload "$tag" "$file" --repo "$repo" --clobber
  awk -v n="$name" -v s="$sha" -v t="$tag" \
    '$1 == n { printf "%-28s %s  %s\n", n, s, t; next } { print }' "$lock" >"$lock.tmp"
  mv "$lock.tmp" "$lock"
done
echo "models.lock updated; commit it to deploy:"
git -C "$root" diff --stat -- deploy/server/models.lock
