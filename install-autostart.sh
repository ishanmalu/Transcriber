#!/usr/bin/env bash
# Keep Transcriber running in the background so http://localhost:5005 is
# always there, like any other bookmark. Undo with ./uninstall-autostart.sh
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/dev.ishanmalu.transcriber.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s|__DIR__|$DIR|g" autostart.plist > "$PLIST"
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Transcriber will now start at login."
echo "Bookmark:  http://localhost:5005"
