#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SKILL_ROOT="${CODEX_HOME:-$HOME/.codex}/skills"
TARGET="$SKILL_ROOT/telegram-local"
mkdir -p "$SKILL_ROOT"
if [ -e "$TARGET" ] || [ -L "$TARGET" ]; then
  if [ "$(readlink "$TARGET" 2>/dev/null || true)" = "$SCRIPT_DIR/skills/telegram-local" ]; then
    echo "Skill already installed."
    exit 0
  fi
  echo "Skill target exists: $TARGET. Keep or remove it explicitly before installing." >&2
  exit 1
fi
ln -s "$SCRIPT_DIR/skills/telegram-local" "$TARGET"
echo "Installed skill. Keep the checkout at this path; restart Codex to discover it."
