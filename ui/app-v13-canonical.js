(() => {
    const num = (value, fallback = 0) => {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    };

    const strategies = () => {
        const base = Array.isArray(MODE_STRATEGIES) ? MODE_STRATEGIES : [];
        const seen = new Set(base);
        const extras = Object.keys(profiles || {}).filter((name) => !seen.has(name));
        return [...base, ...extras].filter((name) => name && name !== 'Manual' && name !== 'Recovered');
    };

    const modeName = (item) => {
        try {
            return normalizedEngineBucket(item);
        } catch {
            return item?.strategy || item?.engine || item?.mode || 'Bot';
        }
    };

    const activeTrades = () => (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade && trade.status === 'active');
    const potentialTrades = () => (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade && trade.status === 'potential');
    const tradesForMode = (name, status) => (status === 'active' ? activeTrades() : potentialTrades()).filter((trade) => modeName(trade) === name);
    const modeRealizedPnl = (name) => num(performanceData?.[name]?.total_pnl, 0);
    const totalModeRealizedPnl = () => strategies().reduce((sum, name) => sum + modeRealizedPnl(name), 0);

    const snapshot = () => {
        const ui = (typeof uiMetricsData === 'object' && uiMetricsData) ? uiMetricsData : {};
        const capital = accountData?.capital || dashboardCapital || {};
        const report = reportData && typeof reportData === 'object' ? reportData : {};
        const active = activeTrades();
        const potential = potentialTrades();
        const activePnl = num(ui.active_pnl ?? active.reduce((sum, trade) => sum + num(trade.pnl, 0), 0), 0);
        const modeRealized = num(ui.mode_realized_pnl ?? totalModeRealizedPnl(), 0);
        const equity = num(ui.account_equity ?? capital.equity ?? accountData?.usdtEq ?? accountData?.totalEq ?? 0, 0);
        const available = num(ui.account_available ?? accountData?.usdtAvail ?? capital.available ?? capital.usdtAvail ?? equity, 0);
        const accountPnl = ui.account_pnl == null ? null : num(ui.account_pnl, 0);
        const sessionPnl = num(ui.session_pnl ?? capital.session_cumulative_pnl ?? modeRealized, 0);
        const growthPnl = accountPnl == null ? sessionPnl : accountPnl;
        const capitalStart = num(ui.capital_start ?? capital.start ?? START_EQUITY, START_EQUITY);
        const capitalTarget = num(ui.capital_target ?? capital.target ?? TARGET_EQUITY, TARGET_EQUITY);
        const goalProgressPct = ui.goal_progress_pct == null ? null : num(ui.goal_progress_pct, 0);
        const snapshotAt = ui.snapshot_at || dashboardSnapshotAt || dashboardSourceState?.snapshotAt || report.server_time || '-';
        return {
            ui,
            capital,
            report,
            activeTrades: active,
            potentialTrades: potential,
            activeCount: num(ui.active_count ?? active.length, active.length),
            potentialCount: num(ui.potential_count ?? potential.length, potential.length),
            activePnl,
            modeRealizedPnl: modeRealized,
            accountPnl,
            sessionPnl,
            growthPnl,
            capitalStart,
            capitalTarget,
            goalProgressPct,
            accountPnlBreakdown: ui.account_pnl_breakdown || {},
            growthSource: ui.sources?.account_pnl || (accountPnl == null ? '來源：/api/trades capital.session_cumulative_pnl' : '來源：/api/trades capital.account_layer_pnl'),
            equity,
            available,
            snapshotAt,
            verdict: report.verdict || (active.length ? 'running' : 'watch'),
            activePnlSource: '來源：/api/trades → OKX 活倉快照 → trade.pnl 合計',
            modeRealizedSource: '來源：/api/trades → performance[四模式].total_pnl 合計',
            equitySource: `來源：/api/trades → capital.equity (${capital.equity_basis || capital.source || 'OKX USDT 權益'})`,
            availableSource: accountData?.usdtAvail != null
                ? '來源：/api/trades → account.usdtAvail'
                : `來源：/api/trades → capital.available (${capital.source || 'OKX USDT 可用餘額'})`,
        };
    };

    getUnifiedReportMetrics = function getUnifiedReportMetricsCanonical() {
        const snap = snapshot();
        return {
            activeCount: snap.activeCount,
            potentialCount: snap.potentialCount,
            activePnl: snap.activePnl,
            sessionActiveCount: snap.activeCount,
            sessionPotentialCount: snap.potentialCount,
            sessionActivePnl: snap.activePnl,
            sessionRealizedPnl: snap.modeRealizedPnl,
            activePnlSource: snap.activePnlSource,
            sessionActiveSource: snap.activePnlSource,
            sessionRealizedSource: snap.modeRealizedSource,
            verdict: snap.verdict,
            protectionRule: snap.report.protection_rule || '-',
            serverTime: snap.snapshotAt,
            positions: Array.isArray(snap.report.positions) ? snap.report.positions : [],
            trackedPositions: Array.isArray(snap.report.tracked_positions) ? snap.report.tracked_positions : [],
            capital: snap.capital,
            capitalSource: snap.equitySource,
        };
    };

    buildStrategyCardModel = function buildStrategyCardModelCanonical(name) {
        const { liveModes, weakModes } = getUnifiedReportModes();
        const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
        const reportMode = reportModes.get(name) || {};
        const stats = strategyStats[name] || {};
        const perf = performanceData[name] || {};
        const opt = optimizerData[name] || {};
        const liveTrades = tradesForMode(name, 'active');
        const candidateTrades = tradesForMode(name, 'potential');
        const livePnl = liveTrades.reduce((sum, trade) => sum + num(trade.pnl, 0), 0);
        const sample = num(perf.sample ?? perf.total_trades, 0);
        return {
            reportMode,
            stats,
            perf,
            opt,
            liveTrades,
            candidateTrades,
            livePnl,
            cumulativePnl: modeRealizedPnl(name),
            cumulativePnlSource: '來源：同一快照 performance.total_pnl',
            winRate: (perf.win_rate == null || sample === 0) ? '-' : pct(perf.win_rate, 1),
            verdict: perf.verdict || stats.verdict || 'learning',
            tierLabel: reportMode.tier ? modeTierLabel(reportMode.tier) : modeTierLabel(opt.state === 'exploit' || opt.state === 'steady' ? 'live_calibration' : 'watch'),
            reasonText: reportMode.reason || verdictDetail(perf),
        };
    };

    refreshSourceBadges = function refreshSourceBadgesCanonical() {
        const snap = snapshot();
        const live = `/api/trades，同步時間：${snap.snapshotAt}`;
        const health = `/api/health-check，同步時間：${healthCheckData?.generated_at || snap.snapshotAt}`;
        [
            ['engine-source', `資料來源口徑：${live}`],
            ['report-source', `資料來源口徑：${live}`],
            ['modes-source', `資料來源口徑：${live}`],
            ['performance-source', `資料來源口徑：${live}`],
            ['health-source', `資料來源口徑：${health}`],
        ].forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = value;
                el.title = value;
            }
        });
    };

    updateOverview = function updateOverviewCanonical() {
        const snap = snapshot();
        const targetProfitGoal = Number(snap.capitalTarget - snap.capitalStart);
        const signedProgress = snap.goalProgressPct == null
            ? (targetProfitGoal !== 0 ? (snap.growthPnl / targetProfitGoal) * 100 : 0)
            : snap.goalProgressPct;
        setTextIfExists('total-equity', money(snap.equity));
        setTextIfExists('usdt-avail', money(snap.available));
        setTextIfExists('version-pnl-label', 'V13 帳戶淨值變化');
        setMetricSource('total-equity', snap.equitySource);
        setMetricSource('usdt-avail', snap.availableSource);
        setMetricSource('total-profit', snap.activePnlSource);
        setMetricSource('capital-change', snap.growthSource);

        const pnlEl = document.getElementById('total-profit');
        if (pnlEl) {
            pnlEl.textContent = `${snap.activePnl >= 0 ? '+' : ''}${money(snap.activePnl)}`;
            pnlEl.className = `value ${snap.activePnl >= 0 ? 'gain' : 'loss'}`;
            pnlEl.title = snap.activePnlSource;
        }

        const capitalChangeEl = document.getElementById('capital-change');
        if (capitalChangeEl) {
            capitalChangeEl.textContent = `${snap.growthPnl >= 0 ? '+' : ''}${money(snap.growthPnl)}`;
            capitalChangeEl.className = snap.growthPnl >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = snap.growthSource;
        }

        updateProgressCurve(snap.growthPnl, signedProgress);
        setTextIfExists('growth-title', snap.accountPnl == null ? 'V13 Session 推算曲線' : 'V13 帳戶淨值曲線');

        const verdictEl = document.getElementById('bot-verdict');
        if (verdictEl) verdictEl.textContent = zhText(snap.verdict);
        const summaryEl = document.getElementById('operator-summary');
        if (summaryEl) {
            summaryEl.innerHTML = `
                <div><span>${snap.activeCount}</span><strong>即時持倉</strong></div>
                <div><span>${snap.potentialCount}</span><strong>候選訊號</strong></div>
                <div><span>${money(snap.activePnl)}</span><strong>活倉浮盈</strong></div>
            `;
        }
    };

    renderBotReport = function renderBotReportCanonical() {
        const box = document.getElementById('bot-report');
        if (!box) return;
        const snap = snapshot();
        box.innerHTML = `
            <div class="health-summary">
                <div class="health-card"><span>目前狀態</span><strong class="${snap.activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(zhText(snap.verdict))}</strong><small>${escapeHtml(snap.snapshotAt)}</small></div>
                <div class="health-card"><span>OKX 活倉未實現盈虧</span><strong class="${snap.activePnl >= 0 ? 'gain' : 'loss'}">${signed(snap.activePnl)}</strong><small>${snap.activeCount} 持倉 / ${snap.potentialCount} 候選</small><small class="metric-source">${escapeHtml(snap.activePnlSource)}</small></div>
                <div class="health-card"><span>四模式已平倉合計</span><strong class="${snap.modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.modeRealizedPnl)}</strong><small>只看 V13 已驗證 closed trades</small><small class="metric-source">${escapeHtml(snap.modeRealizedSource)}</small></div>
                <div class="health-card"><span>資料可信度</span><strong class="good">同一快照</strong><small>/api/trades</small></div>
            </div>
        `;
    };

    renderBotReport = function renderBotReportCanonicalConsistent() {
        const box = document.getElementById('bot-report');
        if (!box) return;
        const snap = snapshot();
        box.innerHTML = `
            <div class="health-summary">
                <div class="health-card"><span>目前狀態</span><strong class="${snap.activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(zhText(snap.verdict))}</strong><small>${escapeHtml(snap.snapshotAt)}</small></div>
                <div class="health-card"><span>OKX 活倉未實現盈虧</span><strong class="${snap.activePnl >= 0 ? 'gain' : 'loss'}">${signed(snap.activePnl)}</strong><small>${snap.activeCount} 持倉 / ${snap.potentialCount} 候選</small><small class="metric-source">${escapeHtml(snap.activePnlSource)}</small></div>
                <div class="health-card"><span>帳戶淨值變化</span><strong class="${snap.growthPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.growthPnl)}</strong><small>${snap.accountPnl == null ? 'Session 推算' : 'OKX 帳戶層'}</small><small class="metric-source">${escapeHtml(snap.growthSource)}</small></div>
                <div class="health-card"><span>四模式已平倉</span><strong class="${snap.modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.modeRealizedPnl)}</strong><small>策略層 closed trades</small><small class="metric-source">${escapeHtml(snap.modeRealizedSource)}</small></div>
            </div>
        `;
    };

    renderEngineHeartbeat = function renderEngineHeartbeatCanonical() {
        const container = document.getElementById('engine-heartbeat');
        if (!container) return;
        container.innerHTML = strategies().map((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const conf = opt.capital_mult != null ? Number(opt.capital_mult).toFixed(2) : (perf.confidence != null ? Number(perf.confidence).toFixed(2) : '1.00');
            return `
                <div class="eng-card">
                    <div class="eng-head"><strong>${escapeHtml(strategyLabel(name))}</strong><span class="eng-verdict">${escapeHtml(verdictLabel(model.verdict || 'learning'))}</span></div>
                    <div class="eng-desc">${escapeHtml(roleText[name] || 'V13 strategy engine')}</div>
                    <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                        <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                        <div><span>信心</span><strong>${escapeHtml(conf)}x</strong></div>
                        <div><span>即時持倉</span><strong>${model.liveTrades.length}</strong></div>
                        <div><span>活倉浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${signed(livePnl, 1)}U</strong><small class="metric-source">OKX 活倉快照</small></div>
                        <div><span>已平倉</span><strong class="${realizedPnl >= 0 ? 'gain' : 'loss'}">${signed(realizedPnl, 1)}U</strong><small class="metric-source">performance.total_pnl</small></div>
                    </div>
                    <div class="eng-scan-status">${model.candidateTrades.length > 0 ? `<span class="eng-scanning">候選 ${model.candidateTrades.length} 筆</span>` : `<span class="eng-idle">等待符合條件</span>`}</div>
                </div>
            `;
        }).join('');
    };

    renderEngineHeartbeat = function renderEngineHeartbeatCanonicalConsistent() {
        const container = document.getElementById('engine-heartbeat');
        if (!container) return;
        const snap = snapshot();
        const totalCard = `
            <div class="eng-card engine-total-card">
                <div class="eng-head"><strong>全引擎一致口徑</strong><span class="eng-verdict">同一快照</span></div>
                <div class="eng-desc">帳戶層看淨值變化；策略層看四模式已平倉；即時層看 OKX 活倉浮盈。</div>
                <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                    <div><span>帳戶淨值變化</span><strong class="${snap.growthPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.growthPnl, 2)}U</strong><small class="metric-source">${escapeHtml(snap.growthSource)}</small></div>
                    <div><span>活倉浮盈合計</span><strong class="${snap.activePnl >= 0 ? 'gain' : 'loss'}">${signed(snap.activePnl, 2)}U</strong><small class="metric-source">${escapeHtml(snap.activePnlSource)}</small></div>
                    <div><span>四模式已平倉</span><strong class="${snap.modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.modeRealizedPnl, 2)}U</strong><small class="metric-source">${escapeHtml(snap.modeRealizedSource)}</small></div>
                    <div><span>目前持倉</span><strong>${snap.activeCount}</strong><small>currentTrades active</small></div>
                    <div><span>候選訊號</span><strong>${snap.potentialCount}</strong><small>currentTrades potential</small></div>
                </div>
            </div>
        `;
        const modeCards = strategies().map((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const conf = opt.capital_mult != null ? Number(opt.capital_mult).toFixed(2) : (perf.confidence != null ? Number(perf.confidence).toFixed(2) : '1.00');
            return `
                <div class="eng-card">
                    <div class="eng-head"><strong>${escapeHtml(strategyLabel(name))}</strong><span class="eng-verdict">${escapeHtml(verdictLabel(model.verdict || 'learning'))}</span></div>
                    <div class="eng-desc">${escapeHtml(roleText[name] || 'V13 strategy engine')}</div>
                    <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                        <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                        <div><span>信心</span><strong>${escapeHtml(conf)}x</strong></div>
                        <div><span>本模式持倉</span><strong>${model.liveTrades.length}</strong></div>
                        <div><span>本模式活倉浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${signed(livePnl, 1)}U</strong><small class="metric-source">OKX 活倉快照</small></div>
                        <div><span>本模式已平倉</span><strong class="${realizedPnl >= 0 ? 'gain' : 'loss'}">${signed(realizedPnl, 1)}U</strong><small class="metric-source">performance.total_pnl</small></div>
                    </div>
                    <div class="eng-scan-status">${model.candidateTrades.length > 0 ? `<span class="eng-scanning">候選 ${model.candidateTrades.length} 筆</span>` : `<span class="eng-idle">等待符合條件</span>`}</div>
                </div>
            `;
        }).join('');
        container.innerHTML = totalCard + modeCards;
    };

    renderModeCards = function renderModeCardsCanonical() {
        const container = document.getElementById('mode-cards');
        if (!container) return;
        container.innerHTML = '';
        strategies().forEach((name) => {
            const profile = profiles[name] || {};
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const card = document.createElement('article');
            card.className = 'mode-card';
            card.innerHTML = `
                <div class="mode-card-head"><strong>${escapeHtml(strategyLabel(name))}</strong>${verdictBadge(model.verdict)}</div>
                <p>${escapeHtml(model.tierLabel || '觀察中')}</p>
                <div class="mode-stats">
                    <div><span>即時持倉</span><strong class="${model.liveTrades.length > 0 ? 'gain' : ''}">${model.liveTrades.length}</strong></div>
                    <div><span>候選</span><strong>${model.candidateTrades.length}</strong></div>
                    <div><span>活倉浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}</strong><small class="metric-source">OKX 活倉快照</small></div>
                    <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                    <div><span>期望值</span><strong class="${num(perf.expectancy, 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                    <div><span>PF</span><strong class="${num(perf.profit_factor, 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
                </div>
                <p class="mode-note">${escapeHtml(model.reasonText || '')}</p>
                <p class="mode-note cumulative-note">已平倉合計：${escapeHtml(signed(realizedPnl, 1))}U <span class="metric-source-inline">來源：performance.total_pnl</span></p>
                <div class="rule-line">60U x 1.00 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr || '-'}x ATR / TP ${profile.tp_atr || '-'}x ATR</div>
            `;
            container.appendChild(card);
        });
    };

    renderPerformance = function renderPerformanceCanonical() {
        const tbody = document.getElementById('performance-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        const metaEl = document.getElementById('performance-metadata');
        if (metaEl) {
            const snap = snapshot();
            metaEl.textContent = `資料來源：/api/trades，同步時間：${snap.snapshotAt}。即時欄位看 OKX 活倉快照；學習欄位看 V13 已驗證 closed trades。`;
        }
        const names = strategies().filter((name) => currentStrategyFilter === 'All' || name === currentStrategyFilter);
        if (!names.length) {
            tbody.innerHTML = `<tr><td colspan="8" class="empty">${text.noData}</td></tr>`;
            return;
        }
        names.forEach((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const sample = num(perf.sample ?? perf.total_trades, 0);
            const pf = num(perf.profit_factor, 0);
            const exp = num(perf.expectancy, 0);
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${escapeHtml(strategyLabel(name))}</strong><small>來源：同一份 /api/trades 快照</small></td>
                <td>${model.liveTrades.length} / ${model.candidateTrades.length}<small>${escapeHtml(verdictLabel(model.verdict || 'learning'))}</small></td>
                <td class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}<small>OKX 活倉快照</small></td>
                <td>${sample} / ${perf.win_rate == null || sample === 0 ? '-' : pct(perf.win_rate, 1)}<small>已驗證 closed trades / 勝率</small></td>
                <td class="${pf >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</td>
                <td><span class="gain">${money(perf.avg_win)}</span> / <span class="loss">${money(perf.avg_loss)}</span></td>
                <td class="${exp >= 0 ? 'gain' : 'loss'}">${money(exp)}</td>
                <td>${verdictBadge(perf.verdict || model.verdict)}<div style="font-size: 10px; color: #a1a1aa; margin-top: 4px; line-height: 1.3;">optimizer：${escapeHtml(optimizerLabel(opt))}<br>已平倉合計：${escapeHtml(signed(model.cumulativePnl, 1))}U</div></td>
            `;
            tbody.appendChild(row);
        });
    };
    renderEngineHeartbeat = function renderEngineHeartbeatCanonicalExplained() {
        const container = document.getElementById('engine-heartbeat');
        if (!container) return;
        const snap = snapshot();
        const b = snap.accountPnlBreakdown || {};
        const startEquity = num(b.session_start_equity ?? snap.capitalStart, 0);
        const currentEquity = num(b.current_account_equity ?? snap.equity, 0);
        const accountChange = num(b.account_pnl ?? snap.growthPnl, 0);
        const verifiedClosed = num(b.verified_mode_closed_pnl ?? snap.modeRealizedPnl, 0);
        const exchangeClosed = num(b.exchange_session_closed_pnl ?? 0, 0);
        const activeUnrealized = num(b.active_unrealized_pnl ?? snap.activePnl, 0);
        const modePlusActive = num(b.mode_closed_plus_active_pnl ?? (verifiedClosed + activeUnrealized), 0);
        const unattributedGap = num(b.unattributed_vs_verified_mode_gap ?? (accountChange - modePlusActive), 0);
        const exchangeGap = num(b.exchange_closed_vs_verified_mode_gap ?? (exchangeClosed - verifiedClosed), 0);
        const accountSessionGap = num(b.account_vs_exchange_session_gap ?? (accountChange - exchangeClosed - activeUnrealized), 0);
        const totalCard = `
            <div class="eng-card engine-total-card">
                <div class="eng-head"><strong>全引擎損益拆解</strong><span class="eng-verdict">同一快照</span></div>
                <div class="eng-desc">帳戶淨值變化不是四模式已平倉；它是 OKX 目前 USDT 淨值扣掉本次啟動基準。</div>
                <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                    <div><span>啟動基準</span><strong>${money(startEquity)}</strong><small>${escapeHtml(b.session_started_at || snap.snapshotAt)}</small></div>
                    <div><span>目前淨值</span><strong>${money(currentEquity)}</strong><small>${escapeHtml(b.equity_basis || 'usdtEq')}</small></div>
                    <div><span>帳戶淨值變化</span><strong class="${accountChange >= 0 ? 'gain' : 'loss'}">${signed(accountChange, 2)}U</strong><small>目前淨值 - 啟動基準</small></div>
                    <div><span>四模式已驗證平倉</span><strong class="${verifiedClosed >= 0 ? 'gain' : 'loss'}">${signed(verifiedClosed, 2)}U</strong><small>performance.total_pnl</small></div>
                    <div><span>活倉浮盈</span><strong class="${activeUnrealized >= 0 ? 'gain' : 'loss'}">${signed(activeUnrealized, 2)}U</strong><small>currentTrades active</small></div>
                </div>
                <div class="eng-stats" style="grid-template-columns: repeat(4, 1fr); margin-top: 8px;">
                    <div><span>四模式+活倉</span><strong class="${modePlusActive >= 0 ? 'gain' : 'loss'}">${signed(modePlusActive, 2)}U</strong><small>已驗證平倉 + 活倉</small></div>
                    <div><span>未歸因差額</span><strong class="${unattributedGap >= 0 ? 'gain' : 'loss'}">${signed(unattributedGap, 2)}U</strong><small>帳戶變化 - 四模式 - 活倉</small></div>
                    <div><span>交易所平倉差</span><strong class="${exchangeGap >= 0 ? 'gain' : 'loss'}">${signed(exchangeGap, 2)}U</strong><small>交易所session平倉 - 已驗證四模式</small></div>
                    <div><span>帳戶/交易所差</span><strong class="${accountSessionGap >= 0 ? 'gain' : 'loss'}">${signed(accountSessionGap, 2)}U</strong><small>費用/資金費/手動/快照差</small></div>
                </div>
            </div>
        `;
        const modeCards = strategies().map((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const conf = opt.capital_mult != null ? Number(opt.capital_mult).toFixed(2) : (perf.confidence != null ? Number(perf.confidence).toFixed(2) : '1.00');
            return `
                <div class="eng-card">
                    <div class="eng-head"><strong>${escapeHtml(strategyLabel(name))}</strong><span class="eng-verdict">${escapeHtml(verdictLabel(model.verdict || 'learning'))}</span></div>
                    <div class="eng-desc">${escapeHtml(roleText[name] || 'V13 strategy engine')}</div>
                    <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                        <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                        <div><span>信心</span><strong>${escapeHtml(conf)}x</strong></div>
                        <div><span>本模式持倉</span><strong>${model.liveTrades.length}</strong></div>
                        <div><span>本模式活倉浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${signed(livePnl, 1)}U</strong><small>OKX 活倉快照</small></div>
                        <div><span>本模式已平倉</span><strong class="${realizedPnl >= 0 ? 'gain' : 'loss'}">${signed(realizedPnl, 1)}U</strong><small>performance.total_pnl</small></div>
                    </div>
                    <div class="eng-scan-status">${model.candidateTrades.length > 0 ? `<span class="eng-scanning">候選 ${model.candidateTrades.length} 筆</span>` : `<span class="eng-idle">等待符合條件</span>`}</div>
                </div>
            `;
        }).join('');
        container.innerHTML = totalCard + modeCards;
    };
    renderEngineHeartbeat = function renderEngineHeartbeatCanonicalMarketMap() {
        const container = document.getElementById('engine-heartbeat');
        if (!container) return;
        const snap = snapshot();
        const b = snap.accountPnlBreakdown || {};
        const ownership = Array.isArray(marketRouterData?.ownership) ? marketRouterData.ownership : [];
        const regimeGuide = [
            ['TREND', 'MacroSniper', '趨勢延伸 / 順勢回踩'],
            ['MEAN_REVERSION', 'MeanReversion', '震盪區間 / 均值回歸'],
            ['EXTREME_REVERSAL', 'Contrarian', '極端衰竭 / 流動性反轉'],
            ['SQUEEZE_BREAKOUT', 'SqueezeHunter', '壓縮後放量突破'],
        ];
        const rowsForState = (stateName) => ownership.filter((row) => row && row.marketState === stateName);
        const symbolsForState = (stateName) => rowsForState(stateName)
            .slice(0, 5)
            .map((row) => String(row.symbol || '').replace('USDT', ''))
            .filter(Boolean)
            .join(', ') || '等待樣本';
        const startEquity = num(b.session_start_equity ?? snap.capitalStart, 0);
        const currentEquity = num(b.current_account_equity ?? snap.equity, 0);
        const accountChange = num(b.account_pnl ?? snap.growthPnl, 0);
        const verifiedClosed = num(b.verified_mode_closed_pnl ?? snap.modeRealizedPnl, 0);
        const activeUnrealized = num(b.active_unrealized_pnl ?? snap.activePnl, 0);
        const modePlusActive = num(b.mode_closed_plus_active_pnl ?? (verifiedClosed + activeUnrealized), 0);
        const unattributedGap = num(b.unattributed_vs_verified_mode_gap ?? (accountChange - modePlusActive), 0);
        const exchangeGap = num(b.exchange_closed_vs_verified_mode_gap ?? 0, 0);
        const accountSessionGap = num(b.account_vs_exchange_session_gap ?? 0, 0);
        const regimeCards = regimeGuide.map(([stateName, owner, purpose]) => {
            const rows = rowsForState(stateName);
            const avgConfidence = rows.length
                ? rows.reduce((sum, row) => sum + num(row.routingConfidence, 0), 0) / rows.length
                : 0;
            return `
                <div>
                    <span>${escapeHtml(stateName)}</span>
                    <strong>${escapeHtml(owner)} · ${rows.length}</strong>
                    <small>${escapeHtml(purpose)}</small>
                    <small class="metric-source">信心 ${avgConfidence.toFixed(2)} / ${escapeHtml(symbolsForState(stateName))}</small>
                </div>
            `;
        }).join('');
        const totalCard = `
            <div class="eng-card engine-total-card">
                <div class="eng-head"><strong>四行情市場對應</strong><span class="eng-verdict">MarketRouter ownership</span></div>
                <div class="eng-desc">這一區只看市場狀態分配，不看各模式自己的候選清單；每個幣只會有一個 activeModeOwner。</div>
                <div class="eng-stats" style="grid-template-columns: repeat(4, 1fr);">
                    ${regimeCards}
                </div>
                <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr); margin-top: 8px;">
                    <div><span>啟動基準</span><strong>${money(startEquity)}</strong><small>${escapeHtml(b.session_started_at || snap.snapshotAt)}</small></div>
                    <div><span>目前淨值</span><strong>${money(currentEquity)}</strong><small>${escapeHtml(b.equity_basis || 'usdtEq')}</small></div>
                    <div><span>帳戶淨值變化</span><strong class="${accountChange >= 0 ? 'gain' : 'loss'}">${signed(accountChange, 2)}U</strong><small>目前淨值 - 啟動基準</small></div>
                    <div><span>四模式已驗證平倉</span><strong class="${verifiedClosed >= 0 ? 'gain' : 'loss'}">${signed(verifiedClosed, 2)}U</strong><small>performance.total_pnl</small></div>
                    <div><span>活倉浮盈</span><strong class="${activeUnrealized >= 0 ? 'gain' : 'loss'}">${signed(activeUnrealized, 2)}U</strong><small>currentTrades active</small></div>
                </div>
                <div class="eng-stats" style="grid-template-columns: repeat(4, 1fr); margin-top: 8px;">
                    <div><span>四模式+活倉</span><strong class="${modePlusActive >= 0 ? 'gain' : 'loss'}">${signed(modePlusActive, 2)}U</strong><small>已驗證平倉 + 活倉</small></div>
                    <div><span>未歸因差額</span><strong class="${unattributedGap >= 0 ? 'gain' : 'loss'}">${signed(unattributedGap, 2)}U</strong><small>帳戶變化 - 四模式 - 活倉</small></div>
                    <div><span>交易所平倉差</span><strong class="${exchangeGap >= 0 ? 'gain' : 'loss'}">${signed(exchangeGap, 2)}U</strong><small>交易所session平倉 - 已驗證四模式</small></div>
                    <div><span>帳戶/交易所差</span><strong class="${accountSessionGap >= 0 ? 'gain' : 'loss'}">${signed(accountSessionGap, 2)}U</strong><small>費用/資金費/手動/快照差</small></div>
                </div>
            </div>
        `;
        const modeCards = strategies().map((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const conf = opt.capital_mult != null ? Number(opt.capital_mult).toFixed(2) : (perf.confidence != null ? Number(perf.confidence).toFixed(2) : '1.00');
            const targetState = ({ MacroSniper: 'TREND', MeanReversion: 'MEAN_REVERSION', Contrarian: 'EXTREME_REVERSAL', SqueezeHunter: 'SQUEEZE_BREAKOUT' })[name] || 'UNKNOWN';
            const ownedRows = ownership.filter((row) => row && row.activeModeOwner === name);
            return `
                <div class="eng-card">
                    <div class="eng-head"><strong>${escapeHtml(strategyLabel(name))}</strong><span class="eng-verdict">${escapeHtml(verdictLabel(model.verdict || 'learning'))}</span></div>
                    <div class="eng-desc">${escapeHtml(targetState)} · ${escapeHtml(roleText[name] || 'V13 strategy engine')}</div>
                    <div class="eng-stats" style="grid-template-columns: repeat(6, 1fr);">
                        <div><span>對應行情</span><strong>${escapeHtml(targetState)}</strong></div>
                        <div><span>分配幣種</span><strong>${ownedRows.length}</strong><small>${escapeHtml(ownedRows.slice(0, 3).map((row) => String(row.symbol || '').replace('USDT', '')).join(', ') || '等待')}</small></div>
                        <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                        <div><span>本模式持倉</span><strong>${model.liveTrades.length}</strong></div>
                        <div><span>本模式活倉浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${signed(livePnl, 1)}U</strong><small>OKX 活倉快照</small></div>
                        <div><span>本模式已平倉</span><strong class="${realizedPnl >= 0 ? 'gain' : 'loss'}">${signed(realizedPnl, 1)}U</strong><small>performance.total_pnl</small></div>
                    </div>
                    <div class="eng-scan-status">${model.candidateTrades.length > 0 ? `<span class="eng-scanning">候選 ${model.candidateTrades.length} 筆 / 信心 ${escapeHtml(conf)}x</span>` : `<span class="eng-idle">等待符合條件</span>`}</div>
                </div>
            `;
        }).join('');
        container.innerHTML = totalCard + modeCards;
    };

    const probeMarginUsdt = 8;
    const modeMarketState = {
        MacroSniper: 'TREND',
        MeanReversion: 'MEAN_REVERSION',
        Contrarian: 'EXTREME_REVERSAL',
        SqueezeHunter: 'SQUEEZE_BREAKOUT',
    };
    const modePurpose = {
        MacroSniper: '趨勢延續與突破追價',
        MeanReversion: '區間震盪後的均值回歸',
        Contrarian: '極端超買超賣後的反轉',
        SqueezeHunter: '低波動擠壓後的放量突破',
    };

    const cleanSource = (label) => String(label || '')
        .replace('api/trades', '/api/trades')
        .replace(/\s+/g, ' ')
        .trim();

    const sampleText = (perf) => {
        const sample = num(perf.sample ?? perf.total_trades, 0);
        const stableMin = num(perf.stable_sample_min, 30);
        return `${sample}/${stableMin}`;
    };

    const modeSizingText = (profile, model) => {
        const marginMult = Number(profile.margin_mult || 1).toFixed(2);
        const sl = profile.sl_atr || '-';
        const tp = profile.tp_atr || '-';
        if (model.trainingLimited) {
            return `訓練探針 ${probeMarginUsdt}U / 嚴格信心門檻 / SL ${sl}x ATR / TP ${tp}x ATR`;
        }
        return `基準 60U x 信心 x ${marginMult} / SL ${sl}x ATR / TP ${tp}x ATR`;
    };

    const modeBadges = (model) => {
        const perf = model.perf || {};
        const badges = [];
        if (model.trainingLimited) badges.push('<span class="mode-badge warning">訓練探針 8U</span>');
        if (perf.execution_blocked) badges.push('<span class="mode-badge warning">暫停開單</span>');
        if (perf.has_effective_sample) badges.push('<span class="mode-badge good">有效樣本</span>');
        if (!perf.stable_sample_ready) badges.push(`<span class="mode-badge">樣本 ${escapeHtml(sampleText(perf))}</span>`);
        return badges.length ? `<div class="mode-badges">${badges.join('')}</div>` : '';
    };

    buildStrategyCardModel = function buildStrategyCardModelReadable(name) {
        const { liveModes, weakModes } = getUnifiedReportModes();
        const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
        const reportMode = reportModes.get(name) || {};
        const stats = strategyStats[name] || {};
        const perf = performanceData[name] || {};
        const opt = optimizerData[name] || {};
        const liveTrades = tradesForMode(name, 'active');
        const candidateTrades = tradesForMode(name, 'potential');
        const livePnl = liveTrades.reduce((sum, trade) => sum + num(trade.pnl, 0), 0);
        const sample = num(perf.sample ?? perf.total_trades, 0);
        const trainingLimited = Boolean(perf.execution_limited || opt.training_probe);
        return {
            reportMode,
            stats,
            perf,
            opt,
            liveTrades,
            candidateTrades,
            livePnl,
            cumulativePnl: modeRealizedPnl(name),
            cumulativePnlSource: '來源：/api/trades performance.total_pnl',
            winRate: (perf.win_rate == null || sample === 0) ? '-' : pct(perf.win_rate, 1),
            verdict: perf.verdict || stats.verdict || 'learning',
            tierLabel: trainingLimited
                ? '負期望訓練中，小單探針收集樣本'
                : (reportMode.tier ? modeTierLabel(reportMode.tier) : modeTierLabel(opt.state === 'exploit' || opt.state === 'steady' ? 'live_calibration' : 'watch')),
            reasonText: perf.execution_probe_reason || reportMode.reason || verdictDetail(perf),
            trainingLimited,
        };
    };

    refreshSourceBadges = function refreshSourceBadgesReadable() {
        const snap = snapshot();
        const live = `/api/trades 更新：${snap.snapshotAt}`;
        const health = `/api/health-check 更新：${healthCheckData?.generated_at || snap.snapshotAt}`;
        [
            ['engine-source', live],
            ['report-source', live],
            ['modes-source', live],
            ['performance-source', live],
            ['health-source', health],
        ].forEach(([id, value]) => {
            const el = document.getElementById(id);
            if (el) {
                el.textContent = value;
                el.title = value;
            }
        });
    };

    updateOverview = function updateOverviewReadable() {
        const snap = snapshot();
        const targetProfitGoal = Number(snap.capitalTarget - snap.capitalStart);
        const signedProgress = snap.goalProgressPct == null
            ? (targetProfitGoal !== 0 ? (snap.growthPnl / targetProfitGoal) * 100 : 0)
            : snap.goalProgressPct;
        setTextIfExists('total-equity', money(snap.equity));
        setTextIfExists('usdt-avail', money(snap.available));
        setTextIfExists('version-pnl-label', '帳戶淨值變化');
        setMetricSource('total-equity', '來源：OKX USDT 權益');
        setMetricSource('usdt-avail', '來源：OKX 可用 USDT');
        setMetricSource('total-profit', '來源：目前持倉即時浮盈');
        setMetricSource('capital-change', '來源：OKX 帳戶層淨值差');

        const pnlEl = document.getElementById('total-profit');
        if (pnlEl) {
            pnlEl.textContent = `${snap.activePnl >= 0 ? '+' : ''}${money(snap.activePnl)}`;
            pnlEl.className = `value ${snap.activePnl >= 0 ? 'gain' : 'loss'}`;
            pnlEl.title = snap.activePnlSource;
        }

        const capitalChangeEl = document.getElementById('capital-change');
        if (capitalChangeEl) {
            capitalChangeEl.textContent = `${snap.growthPnl >= 0 ? '+' : ''}${money(snap.growthPnl)}`;
            capitalChangeEl.className = snap.growthPnl >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = snap.growthSource;
        }

        updateProgressCurve(snap.growthPnl, signedProgress);
        setTextIfExists('growth-title', snap.accountPnl == null ? 'V13 本次啟動損益' : 'V13 帳戶淨值變化');

        const verdictEl = document.getElementById('bot-verdict');
        if (verdictEl) verdictEl.textContent = zhText(snap.verdict);
        const summaryEl = document.getElementById('operator-summary');
        if (summaryEl) {
            summaryEl.innerHTML = `
                <div><span>${snap.activeCount}</span><strong>目前持倉</strong></div>
                <div><span>${snap.potentialCount}</span><strong>候選訊號</strong></div>
                <div><span>${money(snap.activePnl)}</span><strong>持倉浮盈</strong></div>
            `;
        }
    };

    renderBotReport = function renderBotReportReadable() {
        const box = document.getElementById('bot-report');
        if (!box) return;
        const snap = snapshot();
        box.innerHTML = `
            <div class="health-summary">
                <div class="health-card"><span>機器人狀態</span><strong class="${snap.activeCount > 0 ? 'warning' : 'good'}">${escapeHtml(zhText(snap.verdict))}</strong><small>${escapeHtml(snap.snapshotAt)}</small></div>
                <div class="health-card"><span>持倉即時浮盈</span><strong class="${snap.activePnl >= 0 ? 'gain' : 'loss'}">${signed(snap.activePnl)}</strong><small>${snap.activeCount} 持倉 / ${snap.potentialCount} 候選</small><small class="metric-source">來源：currentTrades active pnl</small></div>
                <div class="health-card"><span>帳戶淨值變化</span><strong class="${snap.growthPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.growthPnl)}</strong><small>${snap.accountPnl == null ? 'Session baseline' : 'OKX 帳戶層'}</small><small class="metric-source">${escapeHtml(cleanSource(snap.growthSource))}</small></div>
                <div class="health-card"><span>四模式已平倉</span><strong class="${snap.modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.modeRealizedPnl)}</strong><small>只計入已驗證策略歷史 closed trades</small><small class="metric-source">來源：performance.total_pnl</small></div>
            </div>
        `;
    };

    renderPerformance = function renderPerformanceReadable() {
        const tbody = document.getElementById('performance-body');
        if (!tbody) return;
        tbody.innerHTML = '';
        const metaEl = document.getElementById('performance-metadata');
        if (metaEl) {
            const snap = snapshot();
            metaEl.textContent = `來源：/api/trades，同一快照 ${snap.snapshotAt}；持倉浮盈取 OKX 即時倉位，四模式已平倉取已驗證 closed trades。`;
        }
        const names = strategies().filter((name) => currentStrategyFilter === 'All' || name === currentStrategyFilter);
        if (!names.length) {
            tbody.innerHTML = `<tr><td colspan="8" class="empty">${text.noData}</td></tr>`;
            return;
        }
        names.forEach((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const sample = num(perf.sample ?? perf.total_trades, 0);
            const pf = num(perf.profit_factor, 0);
            const exp = num(perf.expectancy, 0);
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><strong>${escapeHtml(strategyLabel(name))}</strong><small>${escapeHtml(modeMarketState[name] || 'UNKNOWN')}</small></td>
                <td>${model.liveTrades.length} / ${model.candidateTrades.length}<small>${escapeHtml(verdictLabel(model.verdict || 'learning'))}${model.trainingLimited ? ' / 訓練探針' : ''}</small></td>
                <td class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}<small>目前持倉浮盈</small></td>
                <td>${sample} / ${perf.win_rate == null || sample === 0 ? '-' : pct(perf.win_rate, 1)}<small>已驗證樣本 / 勝率</small></td>
                <td class="${pf >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</td>
                <td><span class="gain">${money(perf.avg_win)}</span> / <span class="loss">${money(perf.avg_loss)}</span></td>
                <td class="${exp >= 0 ? 'gain' : 'loss'}">${money(exp)}</td>
                <td>${verdictBadge(perf.verdict || model.verdict)}<div style="font-size: 10px; color: #a1a1aa; margin-top: 4px; line-height: 1.3;">${escapeHtml(optimizerLabel(opt))}<br>已平倉合計：${escapeHtml(signed(model.cumulativePnl, 1))}U${model.trainingLimited ? '<br>限制：8U 訓練探針' : ''}</div></td>
            `;
            tbody.appendChild(row);
        });
    };

    renderModeCards = function renderModeCardsReadable() {
        const container = document.getElementById('mode-cards');
        if (!container) return;
        container.innerHTML = '';
        strategies().forEach((name) => {
            const profile = profiles[name] || {};
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const card = document.createElement('article');
            card.className = 'mode-card';
            card.innerHTML = `
                <div class="mode-card-head"><strong>${escapeHtml(strategyLabel(name))}</strong>${verdictBadge(model.verdict)}</div>
                ${modeBadges(model)}
                <p>${escapeHtml(model.tierLabel || '觀察中')}</p>
                <div class="mode-stats">
                    <div><span>持倉</span><strong class="${model.liveTrades.length > 0 ? 'gain' : ''}">${model.liveTrades.length}</strong></div>
                    <div><span>候選</span><strong>${model.candidateTrades.length}</strong></div>
                    <div><span>浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}</strong><small class="metric-source">OKX 即時倉位</small></div>
                    <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                    <div><span>期望值</span><strong class="${num(perf.expectancy, 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                    <div><span>PF</span><strong class="${num(perf.profit_factor, 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
                </div>
                <p class="mode-note">${escapeHtml(model.reasonText || modePurpose[name] || '')}</p>
                <p class="mode-note cumulative-note">已平倉合計：${escapeHtml(signed(realizedPnl, 1))}U <span class="metric-source-inline">來源：performance.total_pnl</span></p>
                <div class="rule-line">${escapeHtml(modeSizingText(profile, model))}</div>
            `;
            container.appendChild(card);
        });
    };

    renderEngineHeartbeat = function renderEngineHeartbeatReadable() {
        const container = document.getElementById('engine-heartbeat');
        if (!container) return;
        const snap = snapshot();
        const b = snap.accountPnlBreakdown || {};
        const ownership = Array.isArray(marketRouterData?.ownership) ? marketRouterData.ownership : [];
        const regimeGuide = [
            ['TREND', 'MacroSniper', '趨勢延續 / 突破'],
            ['MEAN_REVERSION', 'MeanReversion', '區間震盪 / 均值回歸'],
            ['EXTREME_REVERSAL', 'Contrarian', '極端反轉'],
            ['SQUEEZE_BREAKOUT', 'SqueezeHunter', '擠壓突破'],
        ];
        const rowsForState = (stateName) => ownership.filter((row) => row && row.marketState === stateName);
        const symbolsForState = (stateName) => rowsForState(stateName)
            .slice(0, 5)
            .map((row) => String(row.symbol || '').replace('USDT', ''))
            .filter(Boolean)
            .join(', ') || '無樣本';
        const startEquity = num(b.session_start_equity ?? snap.capitalStart, 0);
        const currentEquity = num(b.current_account_equity ?? snap.equity, 0);
        const accountChange = num(b.account_pnl ?? snap.growthPnl, 0);
        const verifiedClosed = num(b.verified_mode_closed_pnl ?? snap.modeRealizedPnl, 0);
        const activeUnrealized = num(b.active_unrealized_pnl ?? snap.activePnl, 0);
        const modePlusActive = num(b.mode_closed_plus_active_pnl ?? (verifiedClosed + activeUnrealized), 0);
        const unattributedGap = num(b.unattributed_vs_verified_mode_gap ?? (accountChange - modePlusActive), 0);
        const exchangeGap = num(b.exchange_closed_vs_verified_mode_gap ?? 0, 0);
        const accountSessionGap = num(b.account_vs_exchange_session_gap ?? 0, 0);
        const regimeCards = regimeGuide.map(([stateName, owner, purpose]) => {
            const rows = rowsForState(stateName);
            const avgConfidence = rows.length
                ? rows.reduce((sum, row) => sum + num(row.routingConfidence, 0), 0) / rows.length
                : 0;
            return `
                <div>
                    <span>${escapeHtml(stateName)}</span>
                    <strong>${escapeHtml(owner)}：${rows.length}</strong>
                    <small>${escapeHtml(purpose)}</small>
                    <small class="metric-source">信心 ${avgConfidence.toFixed(2)} / ${escapeHtml(symbolsForState(stateName))}</small>
                </div>
            `;
        }).join('');
        const totalCard = `
            <div class="eng-card engine-total-card">
                <div class="eng-head"><strong>市場對應與帳戶歸因</strong><span class="eng-verdict">MarketRouter ownership</span></div>
                <div class="eng-desc">每個幣種先由 MarketRouter 判斷市場型態，再交給對應模式；帳戶層淨值、四模式已平倉與目前持倉浮盈分開顯示。</div>
                <div class="eng-stats">
                    ${regimeCards}
                </div>
                <div class="eng-stats" style="margin-top: 8px;">
                    <div><span>起始權益</span><strong>${money(startEquity)}</strong><small>${escapeHtml(b.session_started_at || snap.snapshotAt)}</small></div>
                    <div><span>目前權益</span><strong>${money(currentEquity)}</strong><small>${escapeHtml(b.equity_basis || 'usdtEq')}</small></div>
                    <div><span>帳戶淨值變化</span><strong class="${accountChange >= 0 ? 'gain' : 'loss'}">${signed(accountChange, 2)}U</strong><small>目前權益 - 起始權益</small></div>
                    <div><span>四模式已平倉</span><strong class="${verifiedClosed >= 0 ? 'gain' : 'loss'}">${signed(verifiedClosed, 2)}U</strong><small>performance.total_pnl</small></div>
                    <div><span>持倉浮盈</span><strong class="${activeUnrealized >= 0 ? 'gain' : 'loss'}">${signed(activeUnrealized, 2)}U</strong><small>currentTrades active</small></div>
                    <div><span>四模式 + 持倉</span><strong class="${modePlusActive >= 0 ? 'gain' : 'loss'}">${signed(modePlusActive, 2)}U</strong><small>已平倉 + 浮盈</small></div>
                    <div><span>未歸因差額</span><strong class="${unattributedGap >= 0 ? 'gain' : 'loss'}">${signed(unattributedGap, 2)}U</strong><small>帳戶層 - 四模式 - 持倉</small></div>
                    <div><span>交易所/驗證差</span><strong class="${exchangeGap >= 0 ? 'gain' : 'loss'}">${signed(exchangeGap, 2)}U</strong><small>session closed 差異</small></div>
                    <div><span>帳戶/交易所差</span><strong class="${accountSessionGap >= 0 ? 'gain' : 'loss'}">${signed(accountSessionGap, 2)}U</strong><small>入金、費用、非策略因素</small></div>
                </div>
            </div>
        `;
        const modeCards = strategies().map((name) => {
            const model = buildStrategyCardModel(name);
            const perf = model.perf || {};
            const opt = model.opt || {};
            const livePnl = Number(model.livePnl || 0);
            const realizedPnl = Number(model.cumulativePnl || 0);
            const conf = opt.capital_mult != null ? Number(opt.capital_mult).toFixed(2) : (perf.confidence != null ? Number(perf.confidence).toFixed(2) : '1.00');
            const targetState = modeMarketState[name] || 'UNKNOWN';
            const ownedRows = ownership.filter((row) => row && row.activeModeOwner === name);
            const ownedSymbols = ownedRows.slice(0, 3).map((row) => String(row.symbol || '').replace('USDT', '')).join(', ') || '無';
            return `
                <div class="eng-card">
                    <div class="eng-head"><strong>${escapeHtml(strategyLabel(name))}</strong><span class="eng-verdict">${escapeHtml(verdictLabel(model.verdict || 'learning'))}</span></div>
                    <div class="eng-desc">${escapeHtml(targetState)}：${escapeHtml(modePurpose[name] || roleText[name] || 'V13 strategy engine')}</div>
                    ${modeBadges(model)}
                    <div class="eng-stats">
                        <div><span>目標市場</span><strong>${escapeHtml(targetState)}</strong></div>
                        <div><span>分配幣種</span><strong>${ownedRows.length}</strong><small>${escapeHtml(ownedSymbols)}</small></div>
                        <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                        <div><span>持倉</span><strong>${model.liveTrades.length}</strong></div>
                        <div><span>浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${signed(livePnl, 1)}U</strong><small>OKX 即時倉位</small></div>
                        <div><span>已平倉</span><strong class="${realizedPnl >= 0 ? 'gain' : 'loss'}">${signed(realizedPnl, 1)}U</strong><small>performance.total_pnl</small></div>
                    </div>
                    <div class="eng-scan-status">${model.candidateTrades.length > 0 ? `<span class="eng-scanning">候選 ${model.candidateTrades.length} 筆 / 信心 ${escapeHtml(conf)}x${model.trainingLimited ? ' / 8U 訓練探針' : ''}</span>` : `<span class="eng-idle">目前沒有候選訊號</span>`}</div>
                </div>
            `;
        }).join('');
        container.innerHTML = totalCard + modeCards;
    };

    const cleanStaticUiLabels = () => {
        const set = (selector, value) => {
            const el = document.querySelector(selector);
            if (el) el.textContent = value;
        };
        set('#version-banner .version-banner-main strong', '零起點已啟用');
        set('#version-banner-state', '本機乾淨訓練資料已啟用');
        set('#growth-title', 'V13 帳戶淨值變化');
        set('#version-pnl-label', '帳戶淨值變化');
        set('#health-check-panel h2', 'V13 健康檢查');
        set('#health-check-state', '載入中...');
        set('#health-check-panel .health-btn', '重新檢查');
        const mlHead = document.querySelector('#ml-log-console')?.closest('section')?.querySelector('h2');
        if (mlHead) mlHead.textContent = 'AI 學習演化紀錄';
        const mlHint = document.querySelector('#ml-log-console')?.closest('section')?.querySelector('.panel-head span[style]');
        if (mlHint) mlHint.textContent = '追蹤策略樣本、參數調整與訓練狀態';
        const mlFirst = document.querySelector('#ml-log-console div');
        if (mlFirst) mlFirst.textContent = '[系統] ML 訓練紀錄載入中...';
    };

    cleanStaticUiLabels();
})();
