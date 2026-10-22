#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  echo "Run ./setup.sh first to install Telegram Local." >&2
  exit 1
fi
export TELEGRAM_LOCAL_HOME="${TELEGRAM_LOCAL_HOME:-${PLUGIN_DATA:-$SCRIPT_DIR/private}}"
exec "$SCRIPT_DIR/.venv/bin/python" -m telegram_local "$@"
