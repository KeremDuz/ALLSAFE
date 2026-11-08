#!/usr/bin/env bash
# Sends a push notification to the server owner's phone through ntfy (https://ntfy.sh).
#
#   notify.sh <title> <message> [priority: default|high|urgent]
#
# The topic URL lives only on the server, in ~/stacks/notify.env (NTFY_URL=https://ntfy.sh/<topic>);
# anyone who knows the topic can read the notifications, so it is a long random name. Without that
# file this script does nothing. Messages carry service names and release ids, never secrets.
set -uo pipefail

STACKS=${ALLSAFE_STACKS_DIR:-$HOME/stacks}
CONFIG="$STACKS/notify.env"
[[ -f $CONFIG ]] || exit 0
NTFY_URL=$(sed -n 's/^NTFY_URL=//p' "$CONFIG" | head -n 1)
[[ $NTFY_URL == https://* ]] || exit 0

title=${1:-ALLSAFE}
message=${2:-}
priority=${3:-default}
case $priority in default | high | urgent) ;; *) priority=default ;; esac
tags=white_check_mark
[[ $priority != default ]] && tags=warning

curl -fsS --max-time 15 -o /dev/null \
  -H "Title: $(hostname): $title" -H "Priority: $priority" -H "Tags: $tags" \
  --data-binary "$message" "$NTFY_URL"
