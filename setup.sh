#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11+ required by the locked dependencies"'
if [ ! -x "$SCRIPT_DIR/.venv/bin/python" ]; then
  "$PYTHON" -m venv "$SCRIPT_DIR/.venv"
fi
"$SCRIPT_DIR/.venv/bin/python" -m pip install -r "$SCRIPT_DIR/requirements.lock"
"$SCRIPT_DIR/.venv/bin/python" -m pip install --no-deps -e "$SCRIPT_DIR"
"$SCRIPT_DIR/.venv/bin/python" -m pip check
echo "Installed. Next: ./run.sh login, then ./run.sh register-codex"
