#!/usr/bin/env bash
# Health check for the home server, run every 5 minutes by cron (# ALLSAFE_MONITOR).
#
# Checks the managed containers, the local service endpoints, the GitHub runner, Tailscale,
# disk and memory. Sends a notification (notify.sh) only when the set of problems changes:
# when something breaks, when the list changes, and once when everything is back to normal.
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
STACKS=${ALLSAFE_STACKS_DIR:-$HOME/stacks}
STATE="$STACKS/.cache/monitor.state"
DISK_LIMIT=${MONITOR_DISK_LIMIT:-85}
MEMORY_FLOOR_MB=${MONITOR_MEMORY_FLOOR_MB:-300}
mkdir -p "$STACKS/.cache"
problems=()

# Containers of the managed stacks (the one-shot migration job is expected to exit).
while IFS='|' read -r name state status project; do
  case $project in phishcatch | allsafe | wazuh | portainer) ;; *) continue ;; esac
  [[ $name == allsafe-migrate-* ]] && continue
  if [[ $state != running ]]; then
    problems+=("$name: $state")
  elif [[ $status == *"(unhealthy)"* ]]; then
    problems+=("$name: unhealthy")
  fi
done < <(docker ps -a --format '{{.Names}}|{{.State}}|{{.Status}}|{{.Label "com.docker.compose.project"}}' 2>/dev/null)

# Endpoints as Tailscale Serve reaches them on loopback.
http_code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@" 2>/dev/null; }
[[ $(http_code http://127.0.0.1:18180/health/ready) == 200 ]] || problems+=("ALLSAFE panel (443) is not ready")
[[ $(http_code http://127.0.0.1:18181/) == 200 ]] || problems+=("public PhishCatch (8443) is not answering")
[[ $(http_code http://127.0.0.1:18190/api/v1/integrations/allsafe/health) == 401 ]] ||
  problems+=("PhishCatch integration gate (10443) is not answering")
[[ $(http_code -k https://127.0.0.1:55000/) == 401 ]] || problems+=("Wazuh API (55000) is not answering")
[[ $(http_code -k https://127.0.0.1:9200/) == 401 ]] || problems+=("Wazuh Indexer (9200) is not answering")

# Services outside Docker.
# Only while a GitHub Actions runner is installed (deploys now poll GitHub instead).
if systemctl list-unit-files 'actions.runner.*' --no-legend 2>/dev/null | grep -q .; then
  systemctl is-active --quiet 'actions.runner.*' || problems+=("GitHub runner service is not running")
fi
[[ $(tailscale status --json 2>/dev/null | jq -r .BackendState 2>/dev/null) == Running ]] ||
  problems+=("Tailscale is not connected")

# Resources.
disk=$(df --output=pcent / | tail -n 1 | tr -dc '0-9')
((disk < DISK_LIMIT)) || problems+=("disk is ${disk}% full")
memory=$(awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo)
((memory >= MEMORY_FLOOR_MB)) || problems+=("only ${memory} MB memory available")

current=$(printf '%s\n' "${problems[@]}" | sed '/^$/d' | LC_ALL=C sort)
previous=$(cat "$STATE" 2>/dev/null)
[[ $current == "$previous" ]] && exit 0
printf '%s\n' "$current" >"$STATE"

if [[ -z $current ]]; then
  bash "$HERE/notify.sh" "Sunucu normale döndü" "Tüm kontroller yeniden başarılı." default
else
  count=$(printf '%s\n' "$current" | wc -l)
  bash "$HERE/notify.sh" "Sunucuda $count sorun" "$(printf '%s\n' "$current" | sed 's/^/- /')" high
fi
