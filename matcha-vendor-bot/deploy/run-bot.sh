#!/usr/bin/env bash
#
# Wrapper used by launchd / cron / systemd. Keeps the scheduler entries
# simple and makes sure the bot always runs from its own directory with the
# right virtualenv.
#
# Make it executable once:  chmod +x deploy/run-bot.sh

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Prefer the project virtualenv; fall back to whatever python3 is on PATH.
if [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
else
    PYTHON="$(command -v python3)"
fi

exec "$PYTHON" -m bot.run "$@"
