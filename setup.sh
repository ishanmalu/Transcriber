#!/usr/bin/env bash
# One-time setup. Creates the virtualenv and installs everything.
set -e
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || { echo "ffmpeg is required:  brew install ffmpeg"; exit 1; }
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
echo
echo "Done. Start it with:  ./Transcriber.command"
