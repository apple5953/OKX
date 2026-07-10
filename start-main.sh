#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODE_NAME="${1:-${OKX_NODE_NAME:-${NODE_NAME:-}}}"
RUN_MODE="${2:-${OKX_RUN_MODE:-demo}}"

if [ -z "${NODE_NAME}" ]; then
    NODE_NAME="$(hostname 2>/dev/null | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^[._-]*//; s/[._-]*$//' | tr '[:upper:]' '[:lower:]')"
fi
if [ -z "${NODE_NAME}" ]; then
    NODE_NAME="node"
fi

export OKX_NODE_NAME="$NODE_NAME"
export NODE_NAME="$NODE_NAME"
export OKX_RUN_MODE="$RUN_MODE"

JOURNAL_PATH="$ROOT_DIR/journal_${NODE_NAME}.json"
TRADE_PATH="$ROOT_DIR/active_trades_${NODE_NAME}.json"

if [ ! -f "$JOURNAL_PATH" ] || [ ! -f "$TRADE_PATH" ]; then
    echo "[Info] First launch detected, running zero-start bootstrap."
    bash "$ROOT_DIR/scripts/bootstrap-zero-start.sh" "$NODE_NAME" "$RUN_MODE"
    exit 0
fi

bash "$ROOT_DIR/run_bot.sh" "$RUN_MODE"
