import os
import datetime
from flask import Flask, jsonify, send_from_directory
from . import state
from . import config
from . import utils
from .utils import as_float, timestamp_ms, json_safe, has_valid_protection
from .okx_client import sync_exchange_history, capital_snapshot, okx, load_local_account_snapshot, fetch_okx_account_snapshot
from .strategies import all_strategy_performance, recent_strategy_stats, get_btc_market_regime, auto_tune_strategy_params, build_bot_report, version_matches_strategy_scope
from .engine import build_live_trade_snapshot, fetch_live_okx_positions, collapse_active_records

app = Flask(__name__, static_folder='../ui')

@app.after_request
def add_no_cache_headers(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0, private'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    response.headers['X-App-Version'] = config.STRATEGY_VERSION
    return response

def serve_ui():
    return send_from_directory('../ui', 'index.html')

@app.route('/')
def serve_root():
    return serve_ui()

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../ui', path)

def build_runtime_status():
    credentials_ready = bool(config.OKX_API_KEY and config.OKX_SECRET and config.OKX_PASSWORD)
    if config.MOCK_MODE:
        return {
            'node_name': config.NODE_NAME,
            'run_mode': 'mock',
            'label': '模擬單',
            'tone': 'mock',
            'detail': '本機只做公開行情與模擬訓練，不送出真實 OKX 委託。',
            'credentials_ready': credentials_ready,
            'whitelist_required': False,
        }
    if config.RUN_MODE == 'live':
        return {
            'node_name': config.NODE_NAME,
            'run_mode': 'live',
            'label': '實盤',
            'tone': 'live',
            'detail': '這台機器會嘗試連到 OKX 並執行真實交易。',
            'credentials_ready': credentials_ready,
            'whitelist_required': True,
        }
    return {
        'node_name': config.NODE_NAME,
        'run_mode': 'auto',
        'label': '自動',
        'tone': 'auto',
        'detail': '有權限時實盤，沒有權限時會退回模擬。',
        'credentials_ready': credentials_ready,
        'whitelist_required': True,
    }

def build_runtime_status_v2():
    credentials_ready = bool(config.OKX_API_KEY and config.OKX_SECRET and config.OKX_PASSWORD)
    node_name = config.NODE_NAME or '-'

    if config.MOCK_MODE:
        return {
            'node_name': node_name,
            'run_mode': 'mock',
            'label': '模擬單',
            'summary': f'模擬單｜{node_name}｜不連 OKX 實盤',
            'tone': 'mock',
            'detail': '目前是模擬模式，會用公開行情與本機資料訓練，不會連到 OKX 實盤下單。',
            'credentials_ready': credentials_ready,
            'whitelist_required': False,
        }

    if config.RUN_MODE == 'demo' or config.DEMO_MODE:
        return {
            'node_name': node_name,
            'run_mode': 'demo',
            'label': '模擬實盤 (Demo)',
            'summary': f"模擬實盤｜{node_name}｜{'API已設定' if credentials_ready else 'API未設定'}",
            'tone': 'live',
            'detail': '目前連接到 OKX 模擬盤 (Sandbox/Demo) 執行模擬實盤交易。',
            'credentials_ready': credentials_ready,
            'whitelist_required': False,
        }

    if config.RUN_MODE == 'live':
        return {
            'node_name': node_name,
            'run_mode': 'live',
            'label': '實盤',
            'summary': f"實盤｜{node_name}｜{'API已設定' if credentials_ready else 'API未設定'}",
            'tone': 'live',
            'detail': '目前會嘗試連到 OKX 實盤；如果憑證或白名單未完成，實盤功能會受限。',
            'credentials_ready': credentials_ready,
            'whitelist_required': True,
        }

    return {
        'node_name': node_name,
        'run_mode': 'auto',
        'label': '自動',
        'summary': f"自動｜{node_name}｜{'API已設定' if credentials_ready else 'API未設定'}",
        'tone': 'auto',
        'detail': '模式會依設定自動切換。若要穩定運作，建議先完成 OKX API 與白名單設定。',
        'credentials_ready': credentials_ready,
        'whitelist_required': True,
    }

def build_account_snapshot():
    account = fetch_okx_account_snapshot(force=True)
    if not isinstance(account, dict):
        account = state.account_data if isinstance(state.account_data, dict) else {}
    if not isinstance(account, dict) or not account:
        account = load_local_account_snapshot() or {}
    account = dict(account) if isinstance(account, dict) else {}
    account.setdefault('totalEq', 0.0)
    account.setdefault('usdtEq', 0.0)
    account.setdefault('usdtAvail', 0.0)
    account.setdefault('source', 'fallback')
    account['capital'] = capital_snapshot()
    return account

def build_health_check_payload(visible_trades=None, live_positions=None, history=None, generated_at=None):
    if live_positions is None:
        live_positions = fetch_live_okx_positions()
    if visible_trades is None:
        visible_trades = [
            t for t in build_live_trade_snapshot(
                tracked_records=collapse_active_records(state.active_trades),
                live_positions=live_positions,
                include_potentials=True,
            )
            if t.get('symbol')
        ]
    if history is None:
        history = sync_exchange_history()

    def trade_issue_item(trade, reasons, category='critical'):
        return {
            'symbol': trade.get('symbol'),
            'instId': trade.get('instId'),
            'direction': trade.get('direction'),
            'strategy': trade.get('strategy'),
            'status': trade.get('status'),
            'source': trade.get('source'),
            'pnl': round(as_float(trade.get('pnl')), 4),
            'entry': as_float(trade.get('entry')),
            'current': as_float(trade.get('current')),
            'sl': as_float(trade.get('sl')),
            'tp1': as_float(trade.get('tp1')),
            'protection_status': trade.get('protection_status') or 'unconfirmed',
            'trailing_stage': trade.get('trailing_stage') or 'waiting',
            'non_blocking_active': bool(trade.get('non_blocking_active')),
            'category': category,
            'reasons': reasons,
        }

    active_trades = [t for t in visible_trades if t.get('status') == 'active']
    bad_trades = []
    protection_warnings = []
    for trade in active_trades:
        reasons = []
        protection_status = str(trade.get('protection_status') or '').lower()
        trailing_stage = str(trade.get('trailing_stage') or '').lower()
        if not has_valid_protection(trade):
            reasons.append('missing TP/SL protection')
        if protection_status in {'failed', 'pending', 'unconfirmed'}:
            reasons.append(f'protection status={protection_status or "unknown"}')
        if trailing_stage == 'protection_failed':
            reasons.append('protection stage failed')
        if trade.get('tp_removed'):
            reasons.append('tp removed')
        if trade.get('non_blocking_active'):
            reasons.append('orphan bypass active')

        if reasons:
            category = 'warning' if trade.get('non_blocking_active') or protection_status in {'confirmed'} else 'critical'
            item = trade_issue_item(trade, reasons, category=category)
            if category == 'warning':
                protection_warnings.append(item)
            else:
                bad_trades.append(item)

    seen_history = set()
    abnormal_training_rows = []
    quarantined_count = 0
    verified_count = 0
    version_mismatch_count = 0
    manual_count = 0
    for row in reversed(history):
        if row.get('status') != 'closed' and not row.get('closed_at'):
            continue
        key = row.get('close_event_key') or row.get('posId') or row.get('closed_at') or row.get('timestamp')
        key = str(key or '')
        if key and key in seen_history:
            continue
        if key:
            seen_history.add(key)

        status = str(row.get('accounting_status') or '').lower()
        strat = str(row.get('strategy') or '')
        reasons = []
        if status == 'quarantined':
            quarantined_count += 1
            reasons.extend(row.get('accounting_reasons') or ['quarantined'])
        elif status == 'verified':
            verified_count += 1
        if row.get('eligible_for_learning') is not True:
            reasons.append('not eligible for learning')
        if not version_matches_strategy_scope(row.get('strategy_version')):
            reasons.append('strategy version out of scope')
            version_mismatch_count += 1
        if strat in {'', 'Manual', 'Mixed'}:
            reasons.append('manual or mixed row')
            manual_count += 1
        if strat and strat not in config.STRATEGY_PROFILES and strat not in {'Manual', 'Mixed'}:
            reasons.append('unknown strategy')
        if reasons:
            abnormal_training_rows.append({
                'symbol': row.get('symbol') or row.get('instId'),
                'strategy': strat or 'Manual',
                'strategy_version': row.get('strategy_version'),
                'accounting_status': status or 'unknown',
                'eligible_for_learning': bool(row.get('eligible_for_learning')),
                'reasons': reasons,
                'closed_at': row.get('closed_at'),
                'realizedPnl': round(as_float(row.get('realizedPnl') or row.get('realized_pnl')), 4),
                'source': row.get('pnl_source') or 'history',
            })

    active_total = len(active_trades)
    bad_trade_count = len(bad_trades)
    warning_count = len(protection_warnings)
    training_issue_count = len(abnormal_training_rows)
    score = 100
    score -= min(50, bad_trade_count * 25)
    score -= min(20, warning_count * 6)
    score -= min(30, training_issue_count * 2)
    score = max(0, score)
    if bad_trade_count > 0:
        status = 'critical'
    elif warning_count > 0 or training_issue_count > 0:
        status = 'warning'
    else:
        status = 'healthy'

    return {
        'status': status,
        'score': score,
        'strategy_version': config.STRATEGY_VERSION,
        'zero_start': utils.load_json_dict(config.ZERO_START_STATE_FILE),
        'generated_at': generated_at or datetime.datetime.now().isoformat(timespec='seconds'),
        'runtime': build_runtime_status_v2(),
        'counts': {
            'active_trades': active_total,
            'bad_trades': bad_trade_count,
            'protection_warnings': warning_count,
            'training_issues': training_issue_count,
            'quarantined_rows': quarantined_count,
            'verified_rows': verified_count,
            'version_mismatch_rows': version_mismatch_count,
            'manual_rows': manual_count,
        },
        'bad_trades': bad_trades[:20],
        'protection_warnings': protection_warnings[:20],
        'abnormal_training_rows': abnormal_training_rows[:20],
        'health_summary': {
            'message': 'healthy' if status == 'healthy' else 'check required',
            'active_blockers': bad_trade_count,
            'training_blockers': training_issue_count,
        },
    }

# --- BACKGROUND SYNC DAEMON INIT ---
state.account_data = load_local_account_snapshot() or {'totalEq': 0.0, 'usdtEq': 0.0, 'usdtAvail': 0.0, 'source': 'init'}

@app.route('/api/trades')
def api_trades():
    try:
        snapshot_at = datetime.datetime.now().isoformat(timespec='seconds')
        # Fetch real-time tickers for potential signals only (Lightweight)
        if state.potential_signals:
            symbols_to_fetch = [t['symbol'] + "/USDT:USDT" for t in state.potential_signals]
            try:
                tickers = okx.fetch_tickers(symbols_to_fetch)
                for t in state.potential_signals:
                    sym = t['symbol'] + "/USDT:USDT"
                    if sym in tickers and tickers[sym].get('last'):
                        t['current'] = float(tickers[sym]['last'])
            except Exception:
                pass

        live_positions = fetch_live_okx_positions()
        visible_trades = build_live_trade_snapshot(
            tracked_records=collapse_active_records(state.active_trades),
            live_positions=live_positions,
            include_potentials=True,
        )
        visible_trades = [t for t in visible_trades if t.get('symbol')]

        account_snapshot = build_account_snapshot()
        state.account_data = account_snapshot

        journal_trades = [t for t in state.trade_journal if t.get('closed_at')]
        first_trade_time = min(t['closed_at'] for t in journal_trades) if journal_trades else None
        last_trade_time = max(t['closed_at'] for t in journal_trades) if journal_trades else None
        zero_start_state = utils.load_json_dict(config.ZERO_START_STATE_FILE)
        health_check = build_health_check_payload(
            visible_trades=visible_trades,
            live_positions=live_positions,
            history=sync_exchange_history(),
            generated_at=snapshot_at,
        )
        resolved_live = [t for t in visible_trades if t.get('status') == 'active']
        return jsonify(json_safe({
            'trades': visible_trades,
            'live_positions': resolved_live,
            'radar': state.market_radar_dict,
            'runtime': build_runtime_status_v2(),
            'regime': get_btc_market_regime(),
            'account': account_snapshot,
            'capital': account_snapshot.get('capital'),
            'profiles': config.STRATEGY_PROFILES,
            'strategy_stats': {name: recent_strategy_stats(name) for name in config.STRATEGY_PROFILES},
            'performance': all_strategy_performance(),
            'optimizer': {name: auto_tune_strategy_params(name) for name in config.STRATEGY_PROFILES},
            'ml_logs': state.ml_evolution_logs,
            'report': build_bot_report(visible_trades, live_positions=live_positions),
            'health_check': health_check,
            'snapshot_at': snapshot_at,
            'strategy_version': config.STRATEGY_VERSION,
            'zero_start': zero_start_state,
            'journal_start': first_trade_time,
            'journal_end': last_trade_time,
        }))
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[api_trades ERROR] {err}")
        return jsonify(json_safe({
            'error': str(e),
            'trades': [],
            'live_positions': [],
            'radar': {},
            'runtime': build_runtime_status_v2(),
            'regime': 'unknown',
            'account': state.account_data,
            'capital': (state.account_data or {}).get('capital'),
            'profiles': {},
            'strategy_stats': {},
            'performance': {},
            'optimizer': {},
            'ml_logs': state.ml_evolution_logs,
            'report': {},
            'health_check': build_health_check_payload(generated_at=datetime.datetime.now().isoformat(timespec='seconds')),
            'snapshot_at': datetime.datetime.now().isoformat(timespec='seconds'),
            'strategy_version': config.STRATEGY_VERSION,
            'zero_start': utils.load_json_dict(config.ZERO_START_STATE_FILE),
            'journal_start': None,
            'journal_end': None,
        })), 200

@app.route('/api/report')
def api_report():
    live_positions = fetch_live_okx_positions()
    visible_trades = [t for t in build_live_trade_snapshot(
        tracked_records=collapse_active_records(state.active_trades),
        live_positions=live_positions,
        include_potentials=True,
    ) if t.get('symbol')]
    return jsonify(json_safe({'report': build_bot_report(visible_trades, live_positions=live_positions), 'live_positions': live_positions, 'runtime': build_runtime_status_v2()}))

@app.route('/api/health-check')
def api_health_check():
    try:
        payload = build_health_check_payload()
        return jsonify(json_safe(payload))
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[api_health_check ERROR] {err}")
        return jsonify(json_safe({
            'status': 'critical',
            'score': 0,
            'strategy_version': config.STRATEGY_VERSION,
            'zero_start': utils.load_json_dict(config.ZERO_START_STATE_FILE),
            'generated_at': datetime.datetime.now().isoformat(timespec='seconds'),
            'runtime': build_runtime_status_v2(),
            'counts': {
                'active_trades': 0,
                'bad_trades': 0,
                'protection_warnings': 0,
                'training_issues': 1,
                'quarantined_rows': 0,
                'verified_rows': 0,
                'version_mismatch_rows': 0,
                'manual_rows': 0,
            },
            'bad_trades': [],
            'protection_warnings': [],
            'abnormal_training_rows': [{
                'strategy': 'system',
                'accounting_status': 'error',
                'eligible_for_learning': False,
                'reasons': [str(e)],
                'source': 'api_health_check',
            }],
            'health_summary': {
                'message': 'health check failed',
                'active_blockers': 0,
                'training_blockers': 1,
            },
        })), 200

@app.route('/api/history')
def api_history():
    try:
        hist = sync_exchange_history(force=True)
        return jsonify(json_safe({
            'history': hist[:config.EXCHANGE_HISTORY_LIMIT],
            'source': 'okx_realized',
            'synced_at': state.exchange_history_synced_at,
            'error': state.exchange_history_error,
        }))
    except Exception as e:
        print(f"History Sync Error: {e}")
        return jsonify({'history': [], 'source': 'okx_realized', 'error': str(e)})

@app.route('/api/journal')
def api_journal():
    return jsonify(json_safe({'journal': state.trade_journal}))

@app.route('/api/performance')
def api_performance():
    return jsonify(json_safe({
        'performance': all_strategy_performance(),
        'optimizer': {name: auto_tune_strategy_params(name) for name in config.STRATEGY_PROFILES},
    }))

@app.route('/api/intelligence')
def api_intelligence():
    # ML intelligence dashboard API
    perf = all_strategy_performance()
    tuned = {name: auto_tune_strategy_params(name, perf[name]) for name in config.STRATEGY_PROFILES}
    
    # Calculate total portfolio stats
    total_trades = sum(p['total_trades'] for p in perf.values())
    total_wins = sum(p['win_count'] for p in perf.values())
    total_losses = sum(p['loss_count'] for p in perf.values())
    win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0
    
    total_pnl = sum(p['total_pnl'] for p in perf.values())
    
    return jsonify(json_safe({
        'performance': perf,
        'tuning': tuned,
        'summary': {
            'total_trades': total_trades,
            'win_rate': round(win_rate, 2),
            'win_count': total_wins,
            'loss_count': total_losses,
            'total_pnl': round(total_pnl, 4),
            'market_regime': get_btc_market_regime()
        },
        'logs': state.ml_evolution_logs
    }))

@app.route('/api/git-pull', methods=['POST'])
def api_git_pull():
    import urllib.request
    import zipfile
    import shutil
    import subprocess
    import sys
    import os
    import threading
    from pathlib import Path

    try:
        # 1. 優先嘗試標準的 Git Pull (如果本機有 Git 且是在 Git 倉庫內)
        has_git = False
        try:
            # 測試系統是否有 git 指令，在沒有 git.exe 的系統上這會直接拋出 FileNotFoundError (WinError 2)
            res = subprocess.run(['git', '--version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if res.returncode == 0:
                has_git = Path(config.PROJECT_DIR).joinpath('.git').exists()
        except (FileNotFoundError, Exception):
            has_git = False

        if has_git:
            # 使用當前使用的分支或預設分支上游更新
            result = subprocess.run(
                ['git', 'pull', 'origin', 'codex/upload-current-bot'],
                capture_output=True,
                text=True,
                cwd=config.PROJECT_DIR,
                encoding='utf-8',
                errors='ignore'
            )
            output = result.stdout or ""
            error = result.stderr or ""
            
            if result.returncode == 0:
                if "Already up to date" in output or "已經是最新的" in output:
                    return jsonify({'success': True, 'updated': False, 'message': "機器人代碼已是最新版本，無需更新。"}), 200
                
                # 自動重啟加載新代碼
                def restart_server():
                    time.sleep(2)
                    os._exit(0)
                threading.Thread(target=restart_server, daemon=True).start()
                return jsonify({'success': True, 'updated': True, 'message': "代碼已透過 Git 同步更新！機器人將在 3 秒內自動重啟加載。"}), 200

        # 2. 如果沒有 Git 環境，則觸發免 Git 綠色更新 (下載 ZIP 解壓覆蓋)
        print("[🔄 ZIP UPDATE] 系統未安裝 Git，啟動免 Git HTTP 更新機制...")
        zip_url = "https://github.com/apple5953/OKX/archive/refs/heads/codex/upload-current-bot.zip"
        temp_zip_path = Path(config.PROJECT_DIR) / "temp_update.zip"
        extract_dir = Path(config.PROJECT_DIR) / "temp_extracted"

        # 下載最新 ZIP 包
        req = urllib.request.Request(zip_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response, open(temp_zip_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)

        # 解壓
        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)

        # 搜尋解壓後的根路徑 (通常會是 OKX-codex-upload-current-bot 目錄)
        extracted_folders = list(extract_dir.glob("*"))
        if not extracted_folders:
            raise Exception("下載的 ZIP 包為空，無法完成更新")

        source_folder = extracted_folders[0]

        # 覆蓋本地核心程式代碼，但排除掉本機獨特的配置文件與 active_trades/journal 以免數據遺失
        # 排除清單
        preserved_files = {
            'active_trades.json', 'global_optimizer.json', 'optimization_cycle_state.json',
            'api_dump.json', 'api_output.json'
        }
        for item in source_folder.rglob("*"):
            if item.is_file():
                # 計算相對路徑
                rel_path = item.relative_to(source_folder)
                target_file_path = Path(config.PROJECT_DIR) / rel_path
                
                # 如果是本機數據庫文件且本地已存在，跳過覆蓋以保護數據
                if rel_path.name in preserved_files and target_file_path.exists():
                    continue
                # 排除本機的專屬設備日誌
                if rel_path.name.startswith("journal_") or rel_path.name.startswith("active_trades_"):
                    continue

                # 確保目標父資料夾存在並覆蓋寫入
                target_file_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, target_file_path)

        # 清理臨時文件
        try:
            shutil.rmtree(extract_dir)
            temp_zip_path.unlink()
        except Exception:
            pass

        # 觸發背景延時重啟以加載更新
        def restart_server_zip():
            time.sleep(2)
            print("[🔄 ZIP UPDATE] 免 Git 更新覆蓋完成，正在重新啟動伺服器...")
            os._exit(0)
        threading.Thread(target=restart_server_zip, daemon=True).start()

        return jsonify({
            'success': True,
            'updated': True,
            'message': "已成功繞過 Git 限制，從 Github 綠色同步更新！機器人將在 3 秒內自動完成平滑重啟。"
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'message': f"同步更新失敗: {str(e)}"}), 500

@app.route('/api/reset-optimizer', methods=['POST'])
def api_reset_optimizer():
    try:
        import shutil
        from pathlib import Path
        
        opt_path = Path(config.PROJECT_DIR) / 'global_optimizer.json'
        state_path = Path(config.PROJECT_DIR) / 'optimization_cycle_state.json'
        
        # 1. 刪除優化器和周期狀態文件 (直接重製數值)
        if opt_path.exists():
            opt_path.unlink()
        if state_path.exists():
            state_path.unlink()
            
        # 2. 清空記憶體緩存日誌與狀態，讓機器人重新冷啟動評估
        state.ml_evolution_logs.append("[🔄 系統重置] 已重置所有模式的自適應優化數值！模式已恢復探索狀態 (Explore)。")
        
        # 3. 觸發一次強制的訓練週期重新生成初始文件
        from .strategies import run_training_cycle
        run_training_cycle(force_history=True)
        
        return jsonify({'success': True, 'message': '所有模式數值已重製成功，自適應優化已重新初始化為探索狀態。'}), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'重製失敗: {str(e)}'}), 500

@app.route('/api/reset-training', methods=['POST'])
def api_reset_training():
    try:
        from . import utils
        from . import state as runtime_state

        result = utils.ensure_zero_start_storage(force=True)

        active_trades = utils.load_json_list(config.TRADE_FILE, 'active trades')
        trade_journal = utils.load_json_list(config.JOURNAL_FILE, 'journal file')

        runtime_state.active_trades[:] = active_trades
        runtime_state.trade_journal[:] = trade_journal
        runtime_state.trade_id_counter = max([trade.get('id', 0) for trade in runtime_state.active_trades], default=0) + 1
        runtime_state.reserved_symbols.clear()
        runtime_state.global_executed_signal_candles.clear()
        runtime_state.global_symbol_cooldowns.clear()
        runtime_state.potential_signals[:] = []
        for key in list(runtime_state.market_radar_dict.keys()):
            runtime_state.market_radar_dict[key] = []
        runtime_state.tuning_log_state.clear()
        with runtime_state.local_account_snapshot_lock:
            runtime_state.local_account_snapshot_cache['fetched_at'] = 0.0
            runtime_state.local_account_snapshot_cache['data'] = None
            runtime_state.local_account_snapshot_cache['source'] = ''
        with runtime_state.account_snapshot_lock:
            runtime_state.account_snapshot_cache['fetched_at'] = 0.0
            runtime_state.account_snapshot_cache['data'] = None
        runtime_state.account_data = {
            'totalEq': 0.0,
            'usdtEq': 0.0,
            'usdtAvail': 0.0,
            'source': 'zero_start_reset',
        }
        runtime_state.ml_evolution_logs.append(
            f"[Zero-Start] training reset requested for {config.NODE_NAME}; backup={result.get('backup_dir', '')}"
        )

        return jsonify({
            'success': True,
            'message': f'訓練已重置，已備份舊資料並從 0 重新開始。備份位置：{result.get("backup_dir", "unknown")}',
            'backup_dir': result.get('backup_dir'),
            'manifest_path': result.get('manifest_path'),
            'strategy_version': config.STRATEGY_VERSION,
            'node_name': config.NODE_NAME,
        }), 200
    except Exception as e:
        return jsonify({'success': False, 'message': f'重置訓練失敗: {str(e)}'}), 500

@app.route('/api/deposit-demo', methods=['POST'])
def api_deposit_demo():
    try:
        from .okx_client import okx
        # 執行 sandbox 充值 API (每次增加 5000 USDT)
        res = okx.private_post_account_demo_adjust_balance({
            'type': 'increase',
            'adjustments': [{'ccy': 'USDT', 'amt': '5000'}]
        })
        # 取得最新餘額
        balance_details = res.get('data', [{}])[0].get('details', [{}])[0]
        bal = balance_details.get('bal', 'N/A')
        return jsonify({
            'success': True,
            'message': f'成功充值 5000 USDT！當前模擬帳戶 USDT 餘額已達: {bal}'
        }), 200
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'充值失敗，今日可能已達次數上限（3次）或發生錯誤: {str(e)}'
        }), 500
