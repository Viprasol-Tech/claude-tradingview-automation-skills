#!/usr/bin/env bash
# Installs every TradingView Automation skill into ~/.claude/skills (Claude Code personal skills).
set -euo pipefail
DEST="${1:-$HOME/.claude/skills}"
SRC="$(cd "$(dirname "$0")" && pwd)/plugins/tradingview-automation/skills"
mkdir -p "$DEST"
for d in "$SRC"/*/; do
  n=$(basename "$d")
  if [ -e "$DEST/$n" ]; then echo "replacing existing $n"; fi
  rm -rf "${DEST:?}/$n"
  cp -r "$d" "$DEST/$n"
  echo "installed $n"
done
echo
echo "Done. Restart Claude Code, then try: \"Lint my TradingView alert message for a webhook bot.\""
