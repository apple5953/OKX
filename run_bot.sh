#!/bin/bash

# ===================================================
#   OKX V12 Harmonic Agent - Mac/Linux Portable Setup
#   Status: Pure Portable (No Install, No Sudo Required)
# ===================================================

# Get current script directory
ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$ROOT_DIR"

RUN_MODE="${1:-${OKX_RUN_MODE:-}}"
if [ -n "$RUN_MODE" ]; then
    export OKX_RUN_MODE="$RUN_MODE"
fi

DEPS_DIR="$ROOT_DIR/.deps"
PORTABLE_PY_DIR="$DEPS_DIR/python-portable"
VENV_DIR="$DEPS_DIR/venv"

echo "==================================================="
echo "  OKX V12 Harmonic Agent - Portable Setup"
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

# 4. Start the server
python3 server.py
