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
export STRATEGY_VERSION="${OKX_STRATEGY_VERSION:-v13}"

MANIFEST_PATH="$ROOT_DIR/zero_start_state_${NODE_NAME}.json"

needs_zero_start() {
    python3 - "$MANIFEST_PATH" <<'PY'
import json
import os
import sys

path = sys.argv[1]
expected = os.environ.get('STRATEGY_VERSION', 'v13').strip().lower()
try:
    with open(path, 'r', encoding='utf-8') as fh:
        payload = json.load(fh)
except Exception:
    print('1')
    raise SystemExit(0)

saved = str(payload.get('strategy_version') or '').strip().lower()
zero_start = bool(payload.get('zero_start_mode'))
print('0' if (zero_start and saved == expected) else '1')
PY
}

if [ ! -f "$MANIFEST_PATH" ] || [ "$(needs_zero_start)" = "1" ]; then
    echo "[Info] Zero-start bootstrap required for V${STRATEGY_VERSION}."
    bash "$ROOT_DIR/scripts/bootstrap-zero-start.sh" "$NODE_NAME" "$RUN_MODE"
    exit 0
fi

bash "$ROOT_DIR/run_bot.sh" "$RUN_MODE"
