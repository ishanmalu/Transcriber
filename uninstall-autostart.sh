#!/usr/bin/env bash
set -e
PLIST="$HOME/Library/LaunchAgents/dev.ishanmalu.transcriber.plist"
launchctl unload "$PLIST" 2>/dev/null || true
rm -f "$PLIST"
echo "Autostart removed."
