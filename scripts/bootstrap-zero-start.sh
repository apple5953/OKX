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
RUN_MODE="${2:-${OKX_RUN_MODE:-${RUN_MODE:-auto}}}"
NODE_NAME="$(sanitize_node_name "$NODE_NAME")"
if [ -z "$NODE_NAME" ]; then
    NODE_NAME="$(default_node_name)"
fi

case "$(printf '%s' "$RUN_MODE" | tr '[:upper:]' '[:lower:]')" in
    mock|simulate|simulation|paper) RUN_MODE="mock" ;;
    demo|sandbox|testnet) RUN_MODE="demo" ;;
    live|real|production) RUN_MODE="live" ;;
    *) RUN_MODE="auto" ;;
esac

export OKX_NODE_NAME="$NODE_NAME"
export NODE_NAME="$NODE_NAME"
export OKX_RUN_MODE="$RUN_MODE"
STRATEGY_VERSION="${OKX_STRATEGY_VERSION:-v13}"

journal_path="$ROOT_DIR/journal_${NODE_NAME}.json"
trade_path="$ROOT_DIR/active_trades_${NODE_NAME}.json"
legacy_journal="$ROOT_DIR/trade_journal.json"
legacy_trade="$ROOT_DIR/active_trades.json"
account_dump="$ROOT_DIR/api_dump.json"
account_output="$ROOT_DIR/api_output.json"
optimizer_path="$ROOT_DIR/global_optimizer.json"
cycle_state_path="$ROOT_DIR/optimization_cycle_state.json"
zero_start_state="$ROOT_DIR/zero_start_state_${NODE_NAME}.json"
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
backup_and_reset "$account_dump"
backup_and_reset "$account_output"
backup_and_reset "$optimizer_path"
backup_and_reset "$cycle_state_path"
backup_and_reset "$zero_start_state"

printf '[]\n' > "$journal_path"
printf '[]\n' > "$trade_path"
printf '{}\n' > "$optimizer_path"
cat > "$cycle_state_path" <<JSON
{
  "generation": "$STRATEGY_VERSION",
  "last_evaluated_trade_count": 0,
  "completed_cycles": 0,
  "consecutive_positive_cycles": 0,
  "last_checked_at": null,
  "mode": "training_active",
  "summary": {},
  "top_drags": [],
  "strategies": {},
  "notes": ""
}
JSON
cat > "$zero_start_state" <<JSON
{
  "node_name": "$NODE_NAME",
  "strategy_version": "$STRATEGY_VERSION",
  "zero_start_mode": true,
  "bootstrapped_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "reset_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "reset_reason": "manual zero-start bootstrap"
}
JSON

echo "[OK] Zero-start initialized for node: $NODE_NAME"
echo "[OK] Run mode: $RUN_MODE"
echo "[OK] Journal: $journal_path"
echo "[OK] Active trades: $trade_path"
echo "[OK] Backups: $backup_dir"

if [ "${SKIP_LAUNCH:-0}" != "1" ]; then
    export OKX_ZERO_START_READY=1
    bash "$ROOT_DIR/run_bot.sh" "$RUN_MODE"
fi
