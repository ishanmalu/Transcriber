#!/usr/bin/env bash
# Keep Transcriber running in the background so the address is always there,
# like any other bookmark. Undo with ./uninstall-autostart.sh
#
#   ./install-autostart.sh                 # this Mac only (127.0.0.1)
#   ./install-autostart.sh tailscale       # reachable from your other devices
#   ./install-autostart.sh 0.0.0.0         # reachable on your local network
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"

HOST="${1:-127.0.0.1}"
if [ "$HOST" = "tailscale" ]; then
  TS="$(command -v tailscale || echo /usr/local/bin/tailscale)"
  HOST="$("$TS" ip -4 2>/dev/null | head -1)"
  [ -n "$HOST" ] || { echo "Tailscale isn't running or isn't logged in."; exit 1; }
fi
PLIST="$HOME/Library/LaunchAgents/dev.ishanmalu.transcriber.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed -e "s|__DIR__|$DIR|g" -e "s|__HOST__|$HOST|g" autostart.plist > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Transcriber will now start at login, bound to $HOST."
if [ "$HOST" = "127.0.0.1" ]; then
  echo "Bookmark:  http://localhost:5005"
else
  echo "Bookmark:  http://$HOST:5005"
fi
