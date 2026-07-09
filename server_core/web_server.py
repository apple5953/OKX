import os
from flask import Flask, jsonify, send_from_directory
from . import state
from . import config
from .utils import as_float, timestamp_ms, json_safe
from .okx_client import sync_exchange_history, capital_snapshot, okx, load_local_account_snapshot
from .strategies import all_strategy_performance, recent_strategy_stats, get_btc_market_regime, auto_tune_strategy_params, build_bot_report
from .engine import build_live_trade_snapshot, fetch_live_okx_positions, collapse_active_records

app = Flask(__name__, static_folder='../ui')

def serve_ui():
    return send_from_directory('../ui', 'index.html')

@app.route('/')
def serve_root():
    return serve_ui()

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('../ui', path)

# --- BACKGROUND SYNC DAEMON INIT ---
state.account_data = load_local_account_snapshot() or {'totalEq': 0.0, 'usdtEq': 0.0, 'usdtAvail': 0.0, 'source': 'init'}

@app.route('/api/trades')
def api_trades():
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
                    
    journal_trades = [t for t in state.trade_journal if t.get('closed_at')]
    first_trade_time = min(t['closed_at'] for t in journal_trades) if journal_trades else None
    last_trade_time = max(t['closed_at'] for t in journal_trades) if journal_trades else None

    try:
        return jsonify(json_safe({
            'trades': visible_trades,
            'live_positions': live_positions,
            'radar': state.market_radar_dict,
            'regime': get_btc_market_regime(),
            'account': state.account_data,
            'profiles': config.STRATEGY_PROFILES,
            'strategy_stats': {name: recent_strategy_stats(name) for name in config.STRATEGY_PROFILES},
            'performance': all_strategy_performance(),
            'optimizer': {name: auto_tune_strategy_params(name) for name in config.STRATEGY_PROFILES},
            'ml_logs': state.ml_evolution_logs,
            'report': build_bot_report(visible_trades, live_positions=live_positions),
            'strategy_version': config.STRATEGY_VERSION,
            'journal_start': first_trade_time,
            'journal_end': last_trade_time,
        }))
    except Exception as e:
        import traceback
        err = traceback.format_exc()
        print(f"[api_trades ERROR] {err}")
        return jsonify(json_safe({'error': str(e), 'trades': visible_trades, 'radar': {}, 'account': state.account_data, 'profiles': {}, 'strategy_stats': {}, 'performance': {}})), 200

@app.route('/api/report')
def api_report():
    live_positions = fetch_live_okx_positions()
    visible_trades = [t for t in build_live_trade_snapshot(
        tracked_records=collapse_active_records(state.active_trades),
        live_positions=live_positions,
        include_potentials=True,
    ) if t.get('symbol')]
    return jsonify(json_safe({'report': build_bot_report(visible_trades, live_positions=live_positions), 'live_positions': live_positions}))

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
            # 測試系統是否有 git 指令
            subprocess.run(['git', '--version'], capture_output=True)
            has_git = Path(config.PROJECT_DIR).joinpath('.git').exists()
        except Exception:
            pass

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

