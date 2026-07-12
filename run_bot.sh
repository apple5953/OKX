#!/bin/bash

# ===================================================
#   OKX V13 Harmonic Agent - Mac/Linux Portable Setup
#   Status: Pure Portable (No Install, No Sudo Required)
# ===================================================

# Get current script directory
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

RUN_MODE="${1:-${OKX_RUN_MODE:-}}"
if [ -n "$RUN_MODE" ]; then
    export OKX_RUN_MODE="$RUN_MODE"
fi
export STRATEGY_VERSION="${OKX_STRATEGY_VERSION:-v13}"

if [ -z "${NODE_NAME:-}" ]; then
    NODE_NAME="$(python3 -c "from server_core import config; print(config.NODE_NAME)")"
fi
export OKX_NODE_NAME="$NODE_NAME"
export NODE_NAME="$NODE_NAME"

MANIFEST_PATH=""
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

DEPS_DIR="$ROOT_DIR/.deps"
PORTABLE_PY_DIR="$DEPS_DIR/python-portable"
VENV_DIR="$DEPS_DIR/venv"

echo "==================================================="
echo "  OKX V13 Harmonic Agent - Portable Setup"
echo "  Target: Mac/Linux Environment Compatibility"
echo "==================================================="

# 1. Determine OS type
OS_TYPE="$(uname -s)"
echo "[Info] Detected Platform: $OS_TYPE"

# 2. Setup isolated user-space virtual environment
# Unlike Windows which needs a zip download, Mac/Linux has native Python installed by default
# but lacks packages. We create a 100% isolated virtual environment inside .deps/venv.
if [ ! -d "$VENV_DIR" ]; then
    echo "[Info] Creating isolated user-space sandbox environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[Error] python3-venv is missing or failed to initialize."
        echo "Please make sure Python3 is available on your Mac/Linux."
        exit 1
    fi
fi

# 3. Activate venv locally and install packages in user-space
echo "[Info] Upgrading pip & installing dependencies locally..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip
pip install ccxt pandas flask

echo "==================================================="
echo "[Success] Portable Sandbox ready! Starting bot..."
echo "==================================================="

if [ -n "${OKX_RUN_MODE:-}" ]; then
    echo "[Info] Run mode: $OKX_RUN_MODE"
fi

if [ "${OKX_ZERO_START_READY:-0}" != "1" ]; then
    MANIFEST_PATH="$ROOT_DIR/zero_start_state_${NODE_NAME}.json"
    if [ ! -f "$MANIFEST_PATH" ] || [ "$(needs_zero_start)" = "1" ]; then
        echo "[Info] Zero-start bootstrap required for V${STRATEGY_VERSION}."
        bash "$ROOT_DIR/scripts/bootstrap-zero-start.sh" "$NODE_NAME" "$RUN_MODE"
        exit 0
    fi
fi

# Open the local UI after startup unless explicitly disabled.
if [ "${OKX_OPEN_UI:-1}" != "0" ]; then
    (
        sleep 4
        if command -v open >/dev/null 2>&1; then
            open "http://127.0.0.1:5000" >/dev/null 2>&1
        elif command -v xdg-open >/dev/null 2>&1; then
            xdg-open "http://127.0.0.1:5000" >/dev/null 2>&1
        fi
    ) >/dev/null 2>&1 &
fi

# 4. Start the server
python3 server.py
