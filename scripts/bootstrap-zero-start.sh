#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

sanitize_node_name() {
    printf '%s' "${1:-}" | tr -cs 'A-Za-z0-9._-' '-' | sed 's/^[._-]*//; s/[._-]*$//'
}

default_node_name() {
    local host
    host="$(sanitize_node_name "$(hostname 2>/dev/null || echo node)")"
    [ -n "$host" ] || host="node"
    printf '%s' "$(printf '%s' "$host" | tr '[:upper:]' '[:lower:]')"
}

NODE_NAME="${1:-${OKX_NODE_NAME:-${NODE_NAME:-}}}"
NODE_NAME="$(sanitize_node_name "$NODE_NAME")"
if [ -z "$NODE_NAME" ]; then
    NODE_NAME="$(default_node_name)"
fi

export OKX_NODE_NAME="$NODE_NAME"
export NODE_NAME="$NODE_NAME"

journal_path="$ROOT_DIR/journal_${NODE_NAME}.json"
trade_path="$ROOT_DIR/active_trades_${NODE_NAME}.json"
legacy_journal="$ROOT_DIR/trade_journal.json"
legacy_trade="$ROOT_DIR/active_trades.json"
backup_dir="$ROOT_DIR/backups/zero-start-$(date +%Y%m%d-%H%M%S)"

mkdir -p "$backup_dir"

backup_and_reset() {
    local path="$1"
    if [ -f "$path" ]; then
        mv "$path" "$backup_dir/$(basename "$path")"
    fi
}

backup_and_reset "$journal_path"
backup_and_reset "$trade_path"
backup_and_reset "$legacy_journal"
backup_and_reset "$legacy_trade"

printf '[]\n' > "$journal_path"
printf '[]\n' > "$trade_path"

echo "[OK] Zero-start initialized for node: $NODE_NAME"
echo "[OK] Journal: $journal_path"
echo "[OK] Active trades: $trade_path"
echo "[OK] Backups: $backup_dir"

if [ "${SKIP_LAUNCH:-0}" != "1" ]; then
    bash "$ROOT_DIR/run_bot.sh"
fi
