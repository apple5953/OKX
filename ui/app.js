let currentTrades = [];
let historyData = [];
let radarData = {};
let profiles = {};
let strategyStats = {};
let performanceData = {};
let optimizerData = {};
let sessionStrategyStats = {};
let sessionPerformanceData = {};
let sessionOptimizerData = {};
let sessionReportData = { live_modes: [], weak_modes: [] };
let accountData = {};
let reportData = {};
let currentStrategyFilter = 'All';
let latestRegime = 'ranging';
let currentStrategyVersion = 'v9';

const START_EQUITY = 5000;
const TARGET_EQUITY = 10000;

const text = {
    all: '\u5168\u90e8',
    active: '\u6301\u5009',
    potential: '\u5019\u9078',
    ready: '\u7b49\u5f85\u689d\u4ef6',
    runner: '\u5954\u8dd1\u4e2d',
    learning: '\u5b78\u7fd2\u4e2d',
    pause: '\u66ab\u505c',
    reduce: '\u964d\u6b0a',
    keep: '\u7dad\u6301',
    scale_up: '\u52a0\u5927',
    scanning: '\u6383\u63cf\u4e2d',
    noData: '\u6682\u7121\u8cc7\u6599'
};

const strategyNames = {
    MacroSniper: '\u8da8\u52e2\u72d9\u64ca',
    MeanReversion: '\u5747\u503c\u4fee\u5fa9',
    Contrarian: '\u6975\u7aef\u53cd\u8f49',
    SqueezeHunter: '\u64e0\u58d3\u7206\u767c',
    Manual: '\u624b\u52d5/\u672a\u540c\u6b65',
    Recovered: '\u6062\u5fa9\u5009\u4f4d',
    Bot: '\u6a5f\u5668\u4eba/\u672a\u5206\u985e',
    Mixed: '\u591a\u7b56\u7565\u6df7\u5408',
};

const roleText = {
    MacroSniper: '\u6293 1H/4H \u5927\u65b9\u5411\uff0c\u9032\u5834\u5c11\uff0c\u76ee\u6a19\u9060\uff0c\u8b93\u5229\u6f64\u5954\u8dd1\u3002',
    MeanReversion: '\u6293\u8d85\u8dcc/\u8d85\u6f32\u5f8c\u7684\u5feb\u901f\u4fee\u5fa9\uff0c\u8f03\u5feb\u4fdd\u672c\u8207\u9396\u5229\u3002',
    Contrarian: '\u53ea\u505a\u6975\u7aef\u53cd\u8f49\uff0c\u9700\u8981 RSI\u3001\u80cc\u96e2\u6216\u6383\u6d41\u52d5\u6027\u8b49\u64da\u3002',
    SqueezeHunter: '\u6293\u6ce2\u52d5\u64e0\u58d3\u5f8c\u7684\u7206\u767c\uff0c\u9806\u52e2\u8ddf\u9032\uff0c\u65e9\u4e00\u9ede\u79fb\u52d5\u6b62\u640d\u3002'
};

const MODE_STRATEGIES = ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'];

const verdictText = {
    scale_up: '\u53ef\u52a0\u5927\u65b0\u55ae',
    keep: '\u6b63\u5e38\u958b\u65b0\u55ae',
    reduce: '\u964d\u4f4e\u5009\u4f4d\u958b\u65b0\u55ae',
    pause: '\u9ad8\u983b\u8a13\u7df4\u55ae',
    learning: '\u5c0f\u55ae\u89c0\u5bdf\u4e2d'
};

const optimizerText = {
    explore: '\u63a2\u7d22\u6536\u6a23\u672c',
    train: '\u9ad8\u983b\u8a13\u7df4',
    recover: '\u964d\u6b0a\u6062\u5fa9',
    steady: '\u7a69\u5b9a\u904b\u884c',
    exploit: '\u653e\u5927\u5954\u8dd1'
};

const reasonMap = [
    ['waiting for PRZ touch', '\u7b49\u5f85\u9032\u5165 PRZ \u5340\u57df'],
    ['invalid live TP/SL direction', 'TP/SL \u65b9\u5411\u4e0d\u5408\u7406'],
    ['OKX has no matching protective SL order', 'OKX 目前找不到對應的止盈止損保護單，可能尚未同步或已被移除'],
    ['profit room too small', '\u5229\u6f64\u7a7a\u9593\u592a\u5c0f'],
    ['mode in training rehab: waiting for base setup', '\u8a13\u7df4\u5fa9\u5065\u4e2d\uff1a\u7b49\u5f85\u57fa\u672c\u689d\u4ef6\u89c0\u5bdf\u55ae'],
    ['training rehab waiting: needs RR >=', '\u8a13\u7df4\u689d\u4ef6\u672a\u9054\u6a19\uff1a\u9700\u8981 RR >='],
    ['training sample allowed: base setup', '\u8a13\u7df4\u89c0\u5bdf\u55ae\u5141\u8a31\uff1a\u57fa\u672c\u689d\u4ef6\u6210\u7acb'],
    ['cooldown active', '\u51b7\u537b\u4e2d'],
    ['MacroSniper needs 1h/4h trend alignment', '\u8da8\u52e2\u72d9\u64ca\u9700\u8981 1H/4H \u540c\u5411'],
    ['MeanReversion will not fight the 1d trend', '\u5747\u503c\u4fee\u5fa9\u4e0d\u9006 1D \u5927\u8da8\u52e2'],
    ['MeanReversion needs RSI stretch', '\u5747\u503c\u4fee\u5fa9\u9700\u8981 RSI \u8d85\u4f38'],
    ['Contrarian blocks triple-timeframe trend crush', '\u6975\u7aef\u53cd\u8f49\u907f\u958b\u4e09\u9031\u671f\u540c\u5411\u78BE\u58D3'],
    ['Contrarian needs exhaustion', '\u6975\u7aef\u53cd\u8f49\u9700\u8981\u8870\u7aed\u8b49\u64da'],
    ['SqueezeHunter needs expansion direction aligned', '\u64e0\u58d3\u7206\u767c\u9700\u8981\u65b9\u5411\u9806\u52e2'],
    ['trend aligned runner setup', '\u8da8\u52e2\u4e00\u81f4\uff0c\u6e96\u5099\u5954\u8dd1'],
    ['mean reversion RSI repair', 'RSI \u4fee\u5fa9\u689d\u4ef6\u6210\u7acb'],
    ['extreme reversal confirmed', '\u6975\u7aef\u53cd\u8f49\u689d\u4ef6\u6210\u7acb'],
    ['squeeze expansion aligned', '\u64e0\u58d3\u7206\u767c\u65b9\u5411\u6210\u7acb']
];

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

const labelMap = [
    ['protection_failed', '\u4fdd\u8b77\u55ae\u5931\u6557'],
    ['mfe_runner_lock', 'MFE \u5954\u8dd1\u9396\u5229'],
    ['mfe_profit_lock', 'MFE \u6d6e\u76c8\u9396\u5229'],
    ['mfe_break_even', 'MFE \u4fdd\u672c\u4fdd\u8b77'],
    ['break_even', '\u4fdd\u672c\u4fdd\u8b77'],
    ['runner', '\u5954\u8dd1\u9396\u5229'],
    ['waiting', '\u7b49\u5f85\u89f8\u767c'],
    ['High Volatility', '\u7206\u91cf\u9ad8\u6ce2\u52d5'],
    ['Squeeze Watch', '\u8cc7\u91d1\u8cbb\u7387\u7570\u5e38'],
    ['Deep Oversold', '\u6975\u7aef\u8d85\u8dcc'],
    ['Rel. Strength', '\u76f8\u5c0d\u5f37\u52e2'],
    ['Majors', '\u4e3b\u6d41\u5e63'],
    ['Default', '\u9810\u8a2d'],
    ['Squeeze', '\u64e0\u58d3'],
    ['Oversold', '\u8d85\u8dcc'],
    ['Bullish', '\u770b\u591a'],
    ['Bearish', '\u770b\u7a7a'],
    ['runner trailing', '\u79fb\u52d5\u6b62\u76c8\u6b62\u640d'],
    ['trail', '\u79fb\u52d5\u6b62\u76c8'],
    ['remove TP', '\u53d6\u6d88\u56fa\u5b9a\u6b62\u76c8'],
    ['BE', '\u4fdd\u672c'],
    ['TP', '\u6b62\u76c8'],
    ['SL', '\u6b62\u640d'],
    ['mfe_runner_lock', 'MFE 奔跑鎖利'],
    ['mfe_profit_lock', 'MFE 浮盈鎖利'],
    ['mfe_break_even', 'MFE 保本保護'],
    ['break_even', '保本保護'],
    ['runner', '奔跑鎖利'],
    ['waiting', '等待觸發'],
    ['manual/unlinked', '\u624b\u52d5/\u672a\u540c\u6b65'],
    ['Manual/Unlinked', '\u624b\u52d5/\u672a\u540c\u6b65'],
    ['Manual', '\u624b\u52d5'],
    ['unlinked', '\u672a\u540c\u6b65']
];

function zhReason(value) {
    if (!value) return text.ready;
    const raw = String(value);
    if (raw.startsWith('training rehab waiting: needs RR >=')) {
        return raw
            .replace('training rehab waiting: needs RR >=', '\u8a13\u7df4\u689d\u4ef6\u672a\u9054\u6a19\uff1a\u9700\u8981 RR >=')
            .replace('and profit room >=', '\uff0c\u5229\u6f64\u7a7a\u9593 >=');
    }
    const item = reasonMap.find(([key]) => raw.includes(key));
    return item ? item[1] : zhText(raw)
        .replace('margin', '\u4fdd\u8b49\u91d1')
        .replace('at', '\u69d3\u687f');
}

function zhText(value) {
    if (!value) return '-';
    let output = String(value);
    labelMap.forEach(([from, to]) => {
        output = output.split(from).join(to);
    });
    return output;
}

function directionLabel(value) {
    const raw = String(value || '').toLowerCase();
    if (raw.includes('long')) return '\u505a\u591a';
    if (raw.includes('short')) return '\u505a\u7a7a';
    if (raw.includes('buy')) return '\u8cb7\u5165';
    if (raw.includes('sell')) return '\u8ce3\u51fa';
    return zhText(value);
}

function protectionLooksAlreadyClosed(trade) {
    const raw = String(trade?.protection_error || '').toLowerCase();
    const exitReason = String(trade?.exit_reason || '').toLowerCase();
    return (
        raw.includes('51169')
        || raw.includes('no positions in this direction')
        || raw.includes('already closed')
        || raw.includes('does not exist')
        || exitReason.includes('position_missing')
    );
}

function protectionLabelV2(trade) {
    const status = String(trade?.protection_status || '').toLowerCase();
    const stage = String(trade?.trailing_stage || '').toLowerCase();
    const errorText = zhReason(trade?.protection_error);
    const checks = Number(trade?.missing_protection_checks || 0);

    if (protectionLooksAlreadyClosed(trade)) {
        return '保護單未回報，但倉位已不存在';
    }
    if (status === 'confirmed' && stage === 'protection_failed') {
        return '保護單已確認，先前同步異常已自動收斂';
    }
    if (status === 'confirmed') return '保護單已確認';
    if (status === 'pending' || status === 'unconfirmed') {
        return checks > 0
            ? `保護單同步中，已檢查 ${checks} 次`
            : '保護單同步中';
    }
    if (status === 'failed' || stage === 'protection_failed') {
        return errorText && errorText !== text.ready
            ? `保護單未確認：${errorText}`
            : '保護單未確認：交易所尚未回報對應保護單';
    }
    if (status === 'emergency_close_submitted') return '保護單異常，已送出緊急平倉';
    return errorText && errorText !== text.ready
        ? `保護單注意：${errorText}`
        : '保護單狀態正常';
}

function protectionLabel(trade) {
    const status = String(trade?.protection_status || '').toLowerCase();
    const stage = String(trade?.trailing_stage || '').toLowerCase();
    const errorText = zhReason(trade?.protection_error);
    if (protectionLooksAlreadyClosed(trade)) {
        return '保護單未回報，但倉位已不存在';
    }
    if (status === 'confirmed' && stage === 'protection_failed') {
        return '止盈止損已確認，但階段仍顯示失敗，正在同步修正';
    }
    if (status === 'confirmed') return '止盈止損已確認';
    if (status === 'failed') {
        return errorText && errorText !== text.ready
            ? `止盈止損未確認：${errorText}`
            : '止盈止損未確認，交易所尚未回報對應保護單';
    }
    if (stage === 'protection_failed') {
        return errorText && errorText !== text.ready
            ? `止盈止損階段異常：${errorText}`
            : '止盈止損階段異常，正在重新同步';
    }
    if (status === 'emergency_close_submitted') return '止盈止損缺失，已送緊急平倉';
    if (status === 'pending') return '止盈止損同步中';
    return errorText && errorText !== text.ready
        ? `止盈止損狀態待確認：${errorText}`
        : '止盈止損狀態待確認';
}

function money(value) {
    const n = Number(value || 0);
    return `${n < 0 ? '-' : ''}$${Math.abs(n).toFixed(2)}`;
}

function num(value, digits = 4) {
    const n = Number(value);
    return Number.isFinite(n) ? n.toFixed(digits) : '-';
}

function pct(value, digits = 1) {
    const n = Number(value || 0);
    return `${n.toFixed(digits)}%`;
}

function signed(value, digits = 2) {
    const n = Number(value || 0);
    return `${n >= 0 ? '+' : ''}${n.toFixed(digits)}`;
}

function strategyLabel(name) {
    return strategyNames[name] || name || '-';
}

function verdictLabel(verdict) {
    return verdictText[verdict] || verdict || '-';
}

function optimizerLabel(opt) {
    if (!opt) return '\u5c1a\u672a\u540c\u6b65';
    return optimizerText[opt.state] || opt.state || '-';
}

function optimizerLine(opt) {
    if (!opt) return '\u81ea\u52d5\u8abf\u53c3\u5c1a\u672a\u540c\u6b65';
    return `\u81ea\u52d5\u8abf\u53c3: ${optimizerLabel(opt)} / \u9032\u5834x${num(opt.tolerance_mult, 2)} / RRx${num(opt.target_rr_mult, 2)} / \u51b7\u537bx${num(opt.cooldown_mult, 2)}`;
}

function verdictDetail(perf) {
    const verdict = perf?.verdict || 'learning';
    if (verdict === 'pause') return '不是整台關掉：此模式仍持續掃描與開 60U 基準訓練單，只是不放大倉位。';
    if (verdict === 'learning') return '\u6a23\u672c\u4e0d\u8db3\uff0c\u53ea\u80fd\u5c0f\u55ae\u6536\u96c6\u6578\u64da\uff1b\u4e0d\u4ee3\u8868\u5df2\u7d93\u80fd\u7a69\u5b9a\u8cfa\u9322\u3002';
    if (verdict === 'reduce') return '\u7e3e\u6548\u9084\u4e0d\u5920\u597d\uff0c\u53ef\u6383\u63cf\u4f46\u61c9\u964d\u4f4e\u5009\u4f4d\u3002';
    if (verdict === 'keep') return '\u76ee\u524d\u7e3e\u6548\u53ef\u7dad\u6301\uff0c\u4e0d\u52a0\u901f\u653e\u5927\u3002';
    if (verdict === 'scale_up') return '\u52dd\u7387\u3001PF \u8207\u671f\u671b\u503c\u9054\u6a19\uff0c\u5141\u8a31\u4fe1\u5fc3\u5009\u4f4d\u653e\u5927\u3002';
    return '-';
}

function filtered(source) {
    if (currentStrategyFilter === 'All') return source;
    return source.filter((item) => {
        const strat = item.strategy || item.strategy_name || '';
        return strat === currentStrategyFilter;
    });
}

function sessionStartedAtMs() {
    const raw = reportData?.session_started_at;
    if (!raw) return 0;
    const parsed = Date.parse(String(raw).replace(' ', 'T'));
    return Number.isFinite(parsed) ? parsed : 0;
}

function rowTimestampMs(row) {
    const info = row?.info || {};
    const candidates = [
        row?.closed_at,
        row?.timestamp,
        row?.lastUpdateTimestamp,
        row?.updated_at,
        row?.created_at,
        row?.opened_at,
        row?.open_timestamp,
        info?.uTime,
        info?.cTime,
    ];
    for (const value of candidates) {
        if (value === null || value === undefined || value === '') continue;
        const numeric = Number(value);
        if (Number.isFinite(numeric) && numeric > 0) {
            return numeric < 1e12 ? Math.floor(numeric * 1000) : Math.floor(numeric);
        }
        const parsed = Date.parse(String(value).replace(' ', 'T'));
        if (Number.isFinite(parsed)) return parsed;
    }
    return 0;
}

function rowStrategyName(row) {
    return row?.strategy || row?.strategy_name || row?.engine || 'Manual';
}

function isSessionRow(row) {
    const startedAt = sessionStartedAtMs();
    if (!startedAt) return true;
    const ts = rowTimestampMs(row);
    return ts > 0 ? ts >= startedAt : false;
}

function sessionHistoryRows() {
    return (Array.isArray(historyData) ? historyData : []).filter(isSessionRow);
}

function sessionActiveTrades() {
    return (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade.status === 'active' && isSessionTrade(trade));
}

function sessionPotentialTrades() {
    return (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade.status === 'potential' && isSessionTrade(trade));
}

function normalizeSessionPnl(row) {
    if (row && row.alphaPnl !== undefined) return Number(row.alphaPnl || 0);
    const realized = Number(row?.realizedPnl ?? row?.realized_pnl ?? row?.pnl ?? 0);
    const funding = Number(row?.fundingFee ?? row?.funding_fee ?? 0);
    return realized - funding;
}

function buildSessionPerformance(rows) {
    const pnls = rows.map((row) => normalizeSessionPnl(row));
    const wins = pnls.filter((pnl) => pnl > 0);
    const losses = pnls.filter((pnl) => pnl < 0);
    const grossProfit = wins.reduce((sum, pnl) => sum + pnl, 0);
    const grossLoss = Math.abs(losses.reduce((sum, pnl) => sum + pnl, 0));
    const sample = pnls.length;
    const winRate = sample ? wins.length / sample : null;
    const avgWin = wins.length ? grossProfit / wins.length : 0;
    const avgLoss = losses.length ? losses.reduce((sum, pnl) => sum + pnl, 0) / losses.length : 0;
    const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : (grossProfit > 0 ? 999.0 : 0.0);
    const expectancy = sample ? pnls.reduce((sum, pnl) => sum + pnl, 0) / sample : 0;

    let maxConsecutiveLosses = 0;
    let streak = 0;
    for (const pnl of pnls) {
        if (pnl < 0) {
            streak += 1;
            maxConsecutiveLosses = Math.max(maxConsecutiveLosses, streak);
        } else {
            streak = 0;
        }
    }

    let equity = 0;
    let peak = 0;
    let maxDrawdown = 0;
    for (const pnl of pnls) {
        equity += pnl;
        peak = Math.max(peak, equity);
        maxDrawdown = Math.min(maxDrawdown, equity - peak);
    }

    let healthScore = 0;
    if (sample >= 20) healthScore += 20;
    else if (sample >= 8) healthScore += 10;
    if (winRate != null) healthScore += Math.max(0, Math.min(1, (winRate - 0.40) / 0.25)) * 25;
    healthScore += Math.max(0, Math.min(1, (profitFactor - 0.80) / 0.80)) * 30;
    healthScore += Math.max(0, Math.min(1, (expectancy + 5) / 15)) * 15;
    healthScore += Math.max(0, Math.min(1, (5 - maxConsecutiveLosses) / 5)) * 10;

    let verdict = 'learning';
    if (sample < 8) verdict = 'learning';
    else if (profitFactor >= 1.35 && expectancy > 0 && maxConsecutiveLosses <= 3) verdict = 'scale_up';
    else if (profitFactor >= 1.0 && expectancy >= 0) verdict = 'keep';
    else if (profitFactor >= 0.75) verdict = 'reduce';
    else verdict = 'pause';

    return {
        sample,
        wins: wins.length,
        losses: losses.length,
        win_rate: winRate,
        gross_profit: Number(grossProfit.toFixed(4)),
        gross_loss: Number(grossLoss.toFixed(4)),
        profit_factor: Number(profitFactor.toFixed(3)),
        avg_win: Number(avgWin.toFixed(4)),
        avg_loss: Number(avgLoss.toFixed(4)),
        payoff_ratio: avgLoss < 0 ? Number((avgWin / Math.abs(avgLoss)).toFixed(3)) : 0.0,
        expectancy: Number(expectancy.toFixed(4)),
        total_pnl: Number(pnls.reduce((sum, pnl) => sum + pnl, 0).toFixed(4)),
        max_win: wins.length ? Number(Math.max(...wins).toFixed(4)) : 0.0,
        max_loss: losses.length ? Number(Math.min(...losses).toFixed(4)) : 0.0,
        max_consecutive_losses: maxConsecutiveLosses,
        max_drawdown: Number(maxDrawdown.toFixed(4)),
        health_score: Number(healthScore.toFixed(1)),
        verdict,
        source: 'session',
        fees_included: true,
        funding_excluded: true,
    };
}

function buildSessionOptimizer(perf) {
    const sample = Number(perf?.sample || 0);
    const pf = Number(perf?.profit_factor || 0);
    const expectancy = Number(perf?.expectancy || 0);
    const maxLossStreak = Number(perf?.max_consecutive_losses || 0);
    const verdict = perf?.verdict || 'learning';

    let state = 'steady';
    let toleranceMult = 1.0;
    let targetRrMult = 1.0;
    let minProfitMult = 1.0;
    let cooldownMult = 1.0;
    let capitalMult = 1.0;
    let maxMargin = 60.0;

    if (sample < 12) {
        state = 'explore';
        toleranceMult = 1.45;
        targetRrMult = 0.70;
        minProfitMult = 0.45;
        cooldownMult = 0.20;
        capitalMult = 0.15;
        maxMargin = 20.0;
    } else if (verdict === 'pause' || pf < 0.75 || expectancy < 0) {
        state = 'train';
        toleranceMult = 1.25;
        targetRrMult = 0.85;
        minProfitMult = 0.50;
        cooldownMult = 0.25;
        capitalMult = pf < 0.60 || expectancy < -1.0 ? 0.12 : 0.25;
        maxMargin = 20.0;
    } else if (verdict === 'reduce') {
        state = 'recover';
        toleranceMult = 1.10;
        targetRrMult = 0.95;
        minProfitMult = 0.75;
        cooldownMult = 0.50;
        capitalMult = 0.45;
        maxMargin = 30.0;
    } else if (verdict === 'scale_up') {
        state = 'exploit';
        toleranceMult = 0.85;
        targetRrMult = 1.10;
        minProfitMult = 1.00;
        cooldownMult = 0.75;
        capitalMult = 1.35;
        maxMargin = 150.0;
    } else {
        state = 'steady';
        toleranceMult = 1.00;
        targetRrMult = 1.00;
        minProfitMult = 1.00;
        cooldownMult = 1.00;
        capitalMult = pf >= 1.10 && expectancy > 0 ? 1.15 : 1.00;
        maxMargin = pf >= 1.10 && expectancy > 0 ? 120.0 : 60.0;
    }

    if (maxLossStreak >= 4 && (expectancy < 0 || pf < 1.0)) {
        targetRrMult *= 0.90;
        minProfitMult *= 0.80;
        cooldownMult *= 0.80;
        capitalMult *= 0.75;
    }

    return {
        state,
        tolerance_mult: Number(toleranceMult.toFixed(3)),
        target_rr_mult: Number(targetRrMult.toFixed(3)),
        min_profit_mult: Number(minProfitMult.toFixed(3)),
        cooldown_mult: Number(Math.max(0.15, Math.min(1.5, cooldownMult)).toFixed(3)),
        capital_mult: Number(Math.max(0.05, Math.min(1.6, capitalMult)).toFixed(3)),
        max_margin: Number(maxMargin.toFixed(2)),
    };
}

function refreshSessionMetrics() {
    const sessionRows = sessionHistoryRows();
    const sessionPerf = {};
    const sessionStats = {};
    const sessionOptimizer = {};
    const sessionLiveModes = [];
    const sessionWeakModes = [];
    MODE_STRATEGIES.forEach((name) => {
        const rows = sessionRows.filter((row) => rowStrategyName(row) === name);
        const perf = buildSessionPerformance(rows);
        const opt = buildSessionOptimizer(perf);
        sessionPerf[name] = perf;
        sessionStats[name] = {
            sample: perf.sample,
            wins: perf.wins,
            losses: perf.losses,
            win_rate: perf.win_rate,
            pnl: perf.total_pnl,
            avg_pnl: perf.expectancy,
            confidence: perf.sample ? Math.max(1, Math.min(2, 0.75 + perf.sample / 25)) : 1,
        };
        sessionOptimizer[name] = opt;
        const item = {
            strategy: name,
            label: strategyLabel(name),
            tier: opt.state === 'exploit' || opt.state === 'steady' ? (perf.verdict === 'scale_up' ? 'live_core' : 'live_calibration') : 'watch',
            reason: verdictDetail(perf),
            pf: perf.profit_factor,
            expectancy: perf.expectancy,
            max_margin: opt.max_margin,
            state: opt.state,
        };
        if (item.tier === 'live_core' || item.tier === 'live_calibration') sessionLiveModes.push(item);
        else sessionWeakModes.push(item);
    });
    sessionPerformanceData = sessionPerf;
    sessionStrategyStats = sessionStats;
    sessionOptimizerData = sessionOptimizer;
    sessionReportData = { live_modes: sessionLiveModes, weak_modes: sessionWeakModes };
    return { sessionRows };
}

function updateProgressCurve(pnlVal, signedProgress) {
    const maxTargetProgress = Math.max(100, signedProgress);
    const progressRatio = Math.max(0, signedProgress) / maxTargetProgress;
    const isDrawdown = signedProgress < 0;
    const x0 = 42;
    const y0 = 132;
    const x = isDrawdown ? x0 : x0 + (556 * progressRatio);
    const y = isDrawdown ? y0 + Math.min(30, Math.abs(signedProgress) * 1.5) : y0 - (94 * progressRatio);
    const x1 = x0 + (x - x0) * 0.25;
    const x2 = x0 + (x - x0) * 0.55;
    const x3 = x0 + (x - x0) * 0.78;
    const y1 = y0 - (y0 - y) * 0.18;
    const y2 = y0 - (y0 - y) * 0.45;
    const y3 = y0 - (y0 - y) * 0.78;
    const progressEl = document.getElementById('growth-progress');
    progressEl.textContent = `${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%`;
    progressEl.className = isDrawdown ? 'loss' : 'gain';
    document.getElementById('progress-curve').setAttribute('points', `${x0},${y0} ${x1},${y1} ${x2},${y2} ${x3},${y3} ${x},${y}`);
    document.getElementById('progress-curve').setAttribute('class', `chart-line${isDrawdown ? ' drawdown' : ''}`);
    document.getElementById('progress-dot').setAttribute('cx', x);
    document.getElementById('progress-dot').setAttribute('cy', y);
    document.getElementById('progress-dot').setAttribute('class', `chart-dot${isDrawdown ? ' drawdown' : ''}`);
    
    const match = currentStrategyVersion.match(/v\d+/i);
    const verTag = match ? match[0].toUpperCase() : 'V9';
    const pnlText = `${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)} USDT`;
    const pctText = `${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%`;

    document.getElementById('curve-label').textContent = `${verTag} 淨損益: ${pnlText} (${pctText})`;
    document.getElementById('curve-label').setAttribute('x', Math.max(60, Math.min(520, x - 28)));
    document.getElementById('curve-label').setAttribute('y', isDrawdown ? 174 : 28);
}

function updateOverview() {
    const activePnl = currentTrades
        .filter((trade) => trade.status === 'active')
        .reduce((sum, trade) => sum + Number(trade.pnl || 0), 0);
    const equity = Number(accountData.usdtEq || accountData.usdtAvail || 0);
    const pnlEl = document.getElementById('total-profit');
    pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
    pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
    document.getElementById('total-equity').textContent = money(equity);
    document.getElementById('usdt-avail').textContent = money(accountData.usdtAvail);
    
    const strategyTotalPnl = Object.values(performanceData || {}).reduce((sum, p) => sum + Number(p.total_pnl || 0), 0);
    const capitalChange = strategyTotalPnl;
    const capitalChangeEl = document.getElementById('capital-change');
    capitalChangeEl.textContent = `${capitalChange >= 0 ? '+' : ''}${money(capitalChange)}`;
    capitalChangeEl.className = capitalChange >= 0 ? 'gain' : 'loss';
    
    const targetProfitGoal = TARGET_EQUITY - START_EQUITY; // 5000
    const signedProgress = (strategyTotalPnl / targetProfitGoal) * 100;
    updateProgressCurve(strategyTotalPnl, signedProgress);

    const match = currentStrategyVersion.match(/v\d+/i);
    const verTag = match ? match[0].toUpperCase() : 'V9';

    const perfList = Object.values(sessionPerformanceData || {});
    const paused = perfList.filter((item) => item.verdict === 'pause').length;
    const active = currentTrades.filter((item) => item.status === 'active').length;
    document.getElementById('bot-verdict').textContent = (accountData.capital || {}).state === 'drawdown'
        ? `${verTag} 策略回撤中（仍持續掃描）`
        : (paused >= 3 ? '四模式持續訓練中' : '正常監控');
    document.getElementById('operator-summary').innerHTML = `
        <div><span>${active}</span><strong>筆持倉</strong></div>
        <div><span>${paused}</span><strong>個模式目前屬於弱勢訓練</strong></div>
        <div><span>${money(activePnl)}</span><strong>\u76ee\u524d\u6d6e\u52d5\u640d\u76ca</strong></div>
    `;
}

function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const liveModes = (sessionReportData.live_modes && sessionReportData.live_modes.length)
        ? sessionReportData.live_modes
        : (reportData.live_modes || []);
    const weakModes = (sessionReportData.weak_modes && sessionReportData.weak_modes.length)
        ? sessionReportData.weak_modes
        : (reportData.weak_modes || []);
    const positions = reportData.positions || [];
    const liveText = liveModes.length
        ? liveModes.map((m) => `${escapeHtml(strategyLabel(m.strategy))} ${escapeHtml(m.tier)} / PF ${escapeHtml(m.pf)} / 上限 ${escapeHtml(money(m.max_margin))}`).join('<br>')
        : '暫無核心模式';
    const weakText = weakModes.length
        ? weakModes.map((m) => `${escapeHtml(strategyLabel(m.strategy))} ${escapeHtml(m.tier)} / PF ${escapeHtml(m.pf)} / 上限 ${escapeHtml(money(m.max_margin))}`).join('<br>')
        : '無弱勢模式';
    const positionText = positions.length
        ? positions.map((p) => `${escapeHtml(p.symbol)} ${escapeHtml(directionLabel(p.direction))} 入場 ${escapeHtml(num(p.entry))} / 現價 ${escapeHtml(num(p.current))} / PnL ${escapeHtml(signed(p.pnl))} / 最高 ${escapeHtml(p.highest_r ?? '-')}R / ${escapeHtml(zhText(p.stage))}`).join('<br>')
        : '目前沒有真實持倉';

    box.innerHTML = `
        <div class="report-main">
            <div><span>目前結論</span><strong>${escapeHtml(zhText(reportData.verdict || '掃描中'))}</strong><small>${escapeHtml(reportData.server_time || '-')}</small></div>
            <div><span>持倉 / 候選</span><strong>${escapeHtml(reportData.active_count || 0)} / ${escapeHtml(reportData.potential_count || 0)}</strong><small>浮動 ${escapeHtml(signed(reportData.active_pnl || 0))}</small></div>
            <div><span>出場保護</span><strong>MFE 鎖利</strong><small>${escapeHtml(zhText(reportData.protection_rule || '-'))}</small></div>
        </div>
        <div class="report-lines">
            <div><span>核心火力</span><p>${liveText}</p></div>
            <div><span>小火力探測</span><p>${weakText}</p></div>
            <div><span>目前單子</span><p>${positionText}</p></div>
        </div>
    `;
}

function showSyncError(error) {
    const verdict = document.getElementById('bot-verdict');
    const summary = document.getElementById('operator-summary');
    if (verdict) verdict.textContent = '\u8cc7\u6599\u540c\u6b65\u7570\u5e38';
    if (summary) {
        summary.innerHTML = `
            <div><span>!</span><strong>\u5f8c\u7aef API \u56de\u61c9\u5931\u6557</strong></div>
            <div><span>--</span><strong>\u4fdd\u7559\u4e0a\u4e00\u7b46\u6709\u6548\u756b\u9762</strong></div>
            <div><span>500</span><strong>${zhText(error?.message || '\u8acb\u67e5\u770b\u65e5\u8a8c')}</strong></div>
        `;
    }
}

function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const liveModes = (sessionReportData.live_modes && sessionReportData.live_modes.length)
        ? sessionReportData.live_modes
        : (reportData.live_modes || []);
    const weakModes = (sessionReportData.weak_modes && sessionReportData.weak_modes.length)
        ? sessionReportData.weak_modes
        : (reportData.weak_modes || []);
    const livePositions = Array.isArray(reportData.positions) ? reportData.positions : [];
    const trackedPositions = Array.isArray(reportData.tracked_positions) ? reportData.tracked_positions : [];
    const positions = livePositions;
    const positionSource = livePositions.length ? 'OKX實際持倉' : 'OKX暫無持倉';
    const sessionActiveCount = Number(reportData.session_active_count ?? 0);
    const sessionPotentialCount = Number(reportData.session_potential_count ?? 0);
    const sessionActivePnl = Number(reportData.session_active_pnl ?? 0);
    const sessionRealizedPnl = Number(reportData.session_realized_pnl ?? 0);

    const liveText = liveModes.length
        ? liveModes.map((m) => `${escapeHtml(strategyLabel(m.strategy))} ${escapeHtml(m.tier)} / PF ${escapeHtml(m.pf)} / margin ${escapeHtml(money(m.max_margin))}`).join('<br>')
        : 'no live mode';
    const weakText = weakModes.length
        ? weakModes.map((m) => `${escapeHtml(strategyLabel(m.strategy))} ${escapeHtml(m.tier)} / PF ${escapeHtml(m.pf)} / margin ${escapeHtml(money(m.max_margin))}`).join('<br>')
        : 'no weak mode';
    const positionText = positions.length
        ? positions.map((p) => `${escapeHtml(positionSource)} · ${escapeHtml(p.symbol)} ${escapeHtml(directionLabel(p.direction))} entry ${escapeHtml(num(p.entry))} / now ${escapeHtml(num(p.current))} / PnL ${escapeHtml(signed(p.pnl))} / ${escapeHtml(zhText(p.stage))}`).join('<br>')
        : (trackedPositions.length ? 'OKX 無持倉，僅有本地追蹤單未顯示為目前倉位' : 'no positions');

    box.innerHTML = `
        <div class="report-main">
            <div><span>report</span><strong>${escapeHtml(zhText(reportData.verdict || '-'))}</strong><small>${escapeHtml(reportData.server_time || '-')}</small></div>
            <div><span>session</span><strong>${escapeHtml(sessionActiveCount)} / ${escapeHtml(sessionPotentialCount)}</strong><small>float ${escapeHtml(signed(sessionActivePnl))} / realized ${escapeHtml(signed(sessionRealizedPnl))}</small></div>
            <div><span>protection</span><strong>MFE</strong><small>${escapeHtml(zhText(reportData.protection_rule || '-'))}</small></div>
        </div>
        <div class="report-lines">
            <div><span>live modes</span><p>${liveText}</p></div>
            <div><span>weak modes</span><p>${weakText}</p></div>
            <div><span>positions</span><p>${positionText}</p></div>
        </div>
    `;
}

function renderModeCards() {
    const container = document.getElementById('mode-cards');
    container.innerHTML = '';
    Object.entries(profiles).forEach(([name, profile]) => {
        const stats = strategyStats[name] || {};
        const perf = performanceData[name] || {};
        const opt = optimizerData[name] || {};
        const pnl = Number(stats.pnl || perf.total_pnl || 0);
        const winRate = (perf.win_rate == null || perf.total_trades === 0) ? '-' : pct(perf.win_rate, 1);
        const card = document.createElement('article');
        card.className = 'mode-card';
        card.innerHTML = `
            <div class="mode-card-head">
                <strong>${strategyLabel(name)}</strong>
                ${verdictBadge(perf.verdict)}
            </div>
            <p>${roleText[name] || profile.role || ''}</p>
            <div class="mode-stats">
                <div><span>\u7e3d\u640d\u76ca</span><strong class="${pnl >= 0 ? 'gain' : 'loss'}">${money(pnl)}</strong></div>
                <div><span>\u52dd\u7387</span><strong>${winRate}</strong></div>
                <div><span>PF</span><strong class="${Number(perf.profit_factor || 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
                <div><span>\u671f\u671b</span><strong class="${Number(perf.expectancy || 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
            </div>
            <p class="mode-note">${verdictDetail(perf)}</p>
            <p class="mode-note optimizer-note">${optimizerLine(opt)}</p>
            <div class="rule-line">60U x \u4fe1\u5fc3 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr}x ATR / TP ${profile.tp_atr}x ATR</div>
        `;
        container.appendChild(card);
    });
}

function verdictBadge(verdict) {
    const klass = verdict === 'scale_up' || verdict === 'keep' ? 'good' : verdict === 'pause' ? 'bad' : 'warn';
    return `<span class="decision ${klass}">${verdictLabel(verdict || 'learning')}</span>`;
}

function renderPerformance() {
    const tbody = document.getElementById('performance-body');
    tbody.innerHTML = '';
    Object.entries(performanceData || {}).forEach(([name, perf]) => {
        if (currentStrategyFilter !== 'All' && name !== currentStrategyFilter) return;
        const pf = Number(perf.profit_factor || 0);
        const exp = Number(perf.expectancy || 0);
        const opt = optimizerData[name] || {};
        const stateLabel = optimizerLabel(opt);
        const tunedAtr = perf.tuned_sl_atr ? `ATR 止損系數: ${perf.tuned_sl_atr}` : '';
        const confidenceText = perf.confidence ? `AI 信心權重: ${perf.confidence}x` : '';
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${strategyLabel(name)}</strong><small>AI 權重: ${perf.weight ?? '1.0'}x / 健康度 ${perf.health_score ?? '-'}</small></td>
            <td>${perf.sample || 0} / ${perf.win_rate == null ? '-' : pct(perf.win_rate * 100, 1)}</td>
            <td class="${pf >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</td>
            <td><span class="gain">${money(perf.avg_win)}</span> / <span class="loss">${money(perf.avg_loss)}</span></td>
            <td class="${exp >= 0 ? 'gain' : 'loss'}">${money(exp)}</td>
            <td>${perf.max_consecutive_losses || 0}</td>
            <td class="loss">${money(perf.max_loss)}<small>回撤 ${money(perf.max_drawdown)}</small></td>
            <td>
                ${verdictBadge(perf.verdict)}
                <div style="font-size: 10px; color: #a1a1aa; margin-top: 4px; line-height: 1.3;">
                    狀態: ${stateLabel}<br>
                    ${tunedAtr} | ${confidenceText}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function renderTrades() {
    const tbody = document.getElementById('trades-body');
    tbody.innerHTML = '';
    const filter = document.querySelector('.tab.active')?.dataset.filter || 'all';
    const rows = filtered(currentTrades).filter((trade) => {
        if (filter === 'active') return trade.status === 'active';
        if (filter === 'potential') return trade.status === 'potential';
        return true;
    });
    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty">${text.noData}</td></tr>`;
        return;
    }
        rows.forEach((trade) => {
        const pnl = Number(trade.pnl || 0);
        const progress = Number(trade.highest_progress || 0);
        const isActive = trade.status === 'active';
        const shownMargin = isActive ? trade.initialMargin : trade.planned_margin;
        const shownNotional = isActive ? trade.notional : trade.planned_notional;
        const shownLeverage = isActive ? trade.leverage : trade.planned_leverage;
        const protectionFailed = trade.protection_status === 'failed' || trade.trailing_stage === 'protection_failed';
        const protectionText = protectionFailed
            ? '\u4fdd\u8b77\u55ae\u5931\u6557'
            : (trade.protection_status === 'confirmed' ? '\u4ea4\u6613\u6240\u5df2\u78ba\u8a8d' : '\u5c1a\u672a\u89f8\u767c');

        // Trailing stop stage badge
        const stage = trade.trailing_stage;
        let stageBadge = '';
        if (stage === 'trailing') stageBadge = '<span class="stage-badge running">\u5954\u8dd1\u4e2d</span>';
        else if (stage === 'break_even') stageBadge = '<span class="stage-badge be">\u4fdd\u672c</span>';
        else if (isActive) stageBadge = '<span class="stage-badge wait">\u7b49\u5f85</span>';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${trade.symbol}</strong><small>${directionLabel(trade.direction)}</small></td>
            <td>${trade.status === 'active' ? '\u6301\u5009\u4e2d' : '\u5019\u9078'}<small>${strategyLabel(trade.strategy)}</small></td>
            <td>${zhReason(trade.block_reason || trade.entry_reason || trade.mode_reason)}</td>
            <td>${num(trade.entry)}<small>\u73fe\u50f9 ${num(trade.current)} / \u6700\u9ad8 ${trade.highest_r ?? '-'}R</small></td>
            <td>${money(shownMargin)}<small>${isActive ? '\u5be6\u969b' : '\u8a08\u756b'} ${shownLeverage || '-'}x / ${money(shownNotional)}</small></td>
            <td><span class="${protectionFailed ? 'loss' : 'gain'}">${protectionFailed ? '\u4fdd\u8b77\u5931\u6557' : (trade.tp_removed ? '\u5954\u8dd1' : num(trade.tp1))}</span><small class="loss">\u6b62\u640d ${num(trade.sl)}</small></td>
            <td><div class="mini-bar"><i style="width:${Math.min(100, progress * 100)}%"></i></div>${stageBadge}<small class="${protectionFailed ? 'loss' : ''}">${protectionText} / ${zhText(trade.runner_policy)}</small></td>
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl)}<small>${signed(trade.percentage || 0)}%</small></td>
        `;
        tbody.appendChild(row);
    });
}

function renderRadar() {
    const tbody = document.getElementById('radar-body');
    tbody.innerHTML = '';
    let rows = [];
    Object.entries(radarData || {}).forEach(([strategy, items]) => {
        if (currentStrategyFilter !== 'All' && strategy !== currentStrategyFilter) return;
        if (Array.isArray(items)) rows = rows.concat(items);
    });
    rows.sort((a, b) => Number(b.score || 0) - Number(a.score || 0));
    rows.slice(0, 80).forEach((item) => {
        const confidence = Number(item.confidence || 1);
        const opt = item.optimizer || optimizerData[item.strategy] || {};
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${item.symbol}</strong><small>RSI ${item.rsi ?? '-'}</small></td>
            <td>${strategyLabel(item.strategy)}<small>${zhText(item.category_key || item.category)} / ${optimizerLabel(opt)}</small></td>
            <td>${zhText(item.pattern || text.scanning)}<small>${zhReason(item.trigger_reason)}</small></td>
            <td>\u4fe1\u5fc3 ${confidence.toFixed(2)}<small>${money(item.planned_margin || 60)} / ${item.planned_leverage || '-'}x</small></td>
            <td>RR ${item.est_rr ?? '-'}<small>\u6b62\u76c8 ${item.est_tp_pct ?? '-'}% / \u6b62\u640d ${item.est_sl_pct ?? '-'}%</small></td>
        `;
        tbody.appendChild(row);
    });
}

function renderHistory() {
    const tbody = document.getElementById('history-body');
    tbody.innerHTML = '';
    const rows = filtered(historyData).slice(0, 80);
    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="empty">${text.noData}</td></tr>`;
        return;
    }
    rows.forEach((item) => {
        const info = item.info || {};
        const pnl = Number(item.realizedPnl || info.realizedPnl || 0);
        const fee = Number(item.fee ?? info.fee ?? 0);
        const funding = Number(item.fundingFee ?? info.fundingFee ?? 0);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${String(item.symbol || '').replace(':USDT', '')}</strong></td>
            <td>${directionLabel(item.direction || info.direction)}</td>
            <td>${strategyLabel(item.strategy)}</td>
            <td>${info.lever || '-'}x</td>
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl, 4)}<small>\u624b\u7e8c\u8cbb ${signed(fee, 4)} / \u8cc7\u91d1\u8cbb ${signed(funding, 4)}</small></td>
            <td>${item.timestamp ? new Date(item.timestamp).toLocaleString() : '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

function renderStrategyInfo() {
    const box = document.getElementById('strategy-info');
    if (currentStrategyFilter === 'All') {
        box.hidden = true;
        return;
    }
    const profile = profiles[currentStrategyFilter] || {};
    const perf = performanceData[currentStrategyFilter] || {};
    const opt = optimizerData[currentStrategyFilter] || {};
    box.hidden = false;
    box.innerHTML = `
        <strong>${strategyLabel(currentStrategyFilter)}</strong>
        <span>${roleText[currentStrategyFilter] || ''}</span>
        <span>PF ${perf.profit_factor ?? '-'} / ${verdictLabel(perf.verdict || 'learning')} / SL ${profile.sl_atr || '-'}x ATR / TP ${profile.tp_atr || '-'}x ATR</span>
        <span>${optimizerLine(opt)}</span>
    `;
}

function updateProgressCurve(pnlVal, signedProgress) {
    const maxTargetProgress = Math.max(100, signedProgress);
    const progressRatio = Math.max(0, signedProgress) / maxTargetProgress;
    const isDrawdown = signedProgress < 0;
    const x0 = 42;
    const y0 = 132;
    const x = isDrawdown ? x0 : x0 + (556 * progressRatio);
    const y = isDrawdown ? y0 + Math.min(30, Math.abs(signedProgress) * 1.5) : y0 - (94 * progressRatio);
    const x1 = x0 + (x - x0) * 0.25;
    const x2 = x0 + (x - x0) * 0.55;
    const x3 = x0 + (x - x0) * 0.78;
    const y1 = y0 - (y0 - y) * 0.18;
    const y2 = y0 - (y0 - y) * 0.45;
    const y3 = y0 - (y0 - y) * 0.78;
    const progressEl = document.getElementById('growth-progress');
    progressEl.textContent = `${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%`;
    progressEl.className = isDrawdown ? 'loss' : 'gain';
    document.getElementById('progress-curve').setAttribute('points', `${x0},${y0} ${x1},${y1} ${x2},${y2} ${x3},${y3} ${x},${y}`);
    document.getElementById('progress-curve').setAttribute('class', `chart-line${isDrawdown ? ' drawdown' : ''}`);
    document.getElementById('progress-dot').setAttribute('cx', x);
    document.getElementById('progress-dot').setAttribute('cy', y);
    document.getElementById('progress-dot').setAttribute('class', `chart-dot${isDrawdown ? ' drawdown' : ''}`);
    
    const match = currentStrategyVersion.match(/v\d+/i);
    const verTag = match ? match[0].toUpperCase() : 'V9';
    const pnlText = `${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)} USDT`;
    const pctText = `${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%`;

    document.getElementById('curve-label').textContent = `${verTag} 淨損益: ${pnlText} (${pctText})`;
    document.getElementById('curve-label').setAttribute('x', Math.max(60, Math.min(520, x - 28)));
    document.getElementById('curve-label').setAttribute('y', isDrawdown ? 174 : 28);
    
    const startLabel = document.getElementById('progress-start-label');
    const targetLabel = document.getElementById('progress-target-label');
    const titleLabel = document.getElementById('growth-title');
    if (startLabel) startLabel.textContent = `0 USDT`;
    if (targetLabel) targetLabel.textContent = `+5000 USDT`;
    if (titleLabel) titleLabel.textContent = `${verTag} 策略累積損益進度`;
}

function updateOverview() {
    const activePnl = currentTrades
        .filter((trade) => trade.status === 'active')
        .reduce((sum, trade) => sum + Number(trade.pnl || 0), 0);
    const equity = Number(accountData.usdtEq || accountData.usdtAvail || 0);
    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail);

    const strategyTotalPnl = Object.values(performanceData || {}).reduce((sum, p) => sum + Number(p.total_pnl || 0), 0);
    const capitalChange = strategyTotalPnl;
    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${capitalChange >= 0 ? '+' : ''}${money(capitalChange)}`;
        capitalChangeEl.className = capitalChange >= 0 ? 'gain' : 'loss';
    }

    const targetProfitGoal = TARGET_EQUITY - START_EQUITY; // 5000
    const signedProgress = (strategyTotalPnl / targetProfitGoal) * 100;
    updateProgressCurve(strategyTotalPnl, signedProgress);

    const match = currentStrategyVersion.match(/v\d+/i);
    const verTag = match ? match[0].toUpperCase() : 'V9';

    const perfList = Object.values(sessionPerformanceData || {});
    const paused = perfList.filter((item) => item.verdict === 'pause').length;
    const active = currentTrades.filter((item) => item.status === 'active').length;
    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) {
        verdictEl.textContent = (accountData.capital || {}).state === 'drawdown'
            ? `${verTag} 策略回撤中（仍持續掃描）`
            : (paused >= 3 ? '四模式持續訓練中' : '正常監控');
    }
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${active}</span><strong>筆持倉</strong></div>
            <div><span>${paused}</span><strong>個模式目前屬於弱勢訓練</strong></div>
            <div><span>${money(activePnl)}</span><strong>目前浮動損益</strong></div>
        `;
    }
}

function renderTrades() {
    const tbody = document.getElementById('trades-body');
    tbody.innerHTML = '';
    const filter = document.querySelector('.tab.active')?.dataset.filter || 'all';
    const rows = filtered(currentTrades).filter((trade) => {
        if (filter === 'active') return trade.status === 'active';
        if (filter === 'potential') return trade.status === 'potential';
        return true;
    });
    if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty">${text.noData}</td></tr>`;
        return;
    }
    rows.forEach((trade) => {
        const pnl = Number(trade.pnl || 0);
        const progress = Number(trade.highest_progress || 0);
        const isActive = trade.status === 'active';
        const shownMargin = isActive ? trade.initialMargin : trade.planned_margin;
        const shownNotional = isActive ? trade.notional : trade.planned_notional;
        const shownLeverage = isActive ? trade.leverage : trade.planned_leverage;
        const protectionFailed = trade.protection_status === 'failed' || trade.trailing_stage === 'protection_failed';
        const protectionText = protectionLabelV2(trade);

        let stageBadge = '';
        if (trade.trailing_stage === 'trailing') stageBadge = '<span class="stage-badge running">\u5954\u8dd1\u4e2d</span>';
        else if (trade.trailing_stage === 'break_even') stageBadge = '<span class="stage-badge be">\u4fdd\u672c</span>';
        else if (isActive) stageBadge = '<span class="stage-badge wait">\u7b49\u5f85</span>';

        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${trade.symbol}</strong><small>${directionLabel(trade.direction)}</small></td>
            <td>${trade.status === 'active' ? '\u6301\u5009\u4e2d' : '\u5019\u9078'}<small>${strategyLabel(trade.strategy)}</small></td>
            <td>${zhReason(trade.block_reason || trade.entry_reason || trade.mode_reason)}</td>
            <td>${num(trade.entry)}<small>\u73fe\u50f9 ${num(trade.current)} / \u6700\u9ad8 ${trade.highest_r ?? '-'}R</small></td>
            <td>${money(shownMargin)}<small>${isActive ? '\u5be6\u969b' : '\u8a08\u756b'} ${shownLeverage || '-'}x / ${money(shownNotional)}</small></td>
            <td><span class="${protectionFailed ? 'loss' : 'gain'}">${protectionFailed ? '\u6b63\u5728\u6aa2\u67e5' : (trade.tp_removed ? '\u5954\u8dd1' : num(trade.tp1))}</span><small class="loss">\u6b62\u640d ${num(trade.sl)}</small></td>
            <td><div class="mini-bar"><i style="width:${Math.min(100, progress * 100)}%"></i></div>${stageBadge}<small class="${protectionFailed ? 'loss' : ''}">${protectionText} / ${zhText(trade.runner_policy)}</small></td>
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl)}<small>${signed(trade.percentage || 0)}%</small></td>
        `;
        tbody.appendChild(row);
    });
}

async function fetchTrades() {
    try {
        const response = await fetch('/api/trades');
        if (!response.ok) throw new Error(`API ${response.status}`);
        const data = await response.json();
        if (data.error) console.warn('api_trades fallback', data.error);
        currentTrades = Array.isArray(data.trades) ? data.trades : [];
        radarData = data.radar && typeof data.radar === 'object' ? data.radar : {};
        latestRegime = data.regime || 'ranging';
        
        // Update Topbar market regime indicator
        const regText = document.getElementById('regime-text');
        const regWrap = document.getElementById('regime-wrapper');
        if (regText && regWrap) {
            if (latestRegime === 'trending') {
                regText.innerHTML = '🟢 單邊趨勢市 📈';
                regWrap.style.background = 'rgba(34, 197, 94, 0.15)';
                regWrap.style.borderColor = 'rgba(34, 197, 94, 0.3)';
                regWrap.style.color = '#22c55e';
            } else {
                regText.innerHTML = '🔵 橫盤震盪市 📉';
                regWrap.style.background = 'rgba(59, 130, 246, 0.15)';
                regWrap.style.borderColor = 'rgba(59, 130, 246, 0.3)';
                regWrap.style.color = '#3b82f6';
            }
        }
        
        accountData = data.account && typeof data.account === 'object' ? data.account : {};
        profiles = data.profiles && typeof data.profiles === 'object' ? data.profiles : profiles;
        strategyStats = data.strategy_stats && typeof data.strategy_stats === 'object' ? data.strategy_stats : strategyStats;
        performanceData = data.performance && typeof data.performance === 'object' ? data.performance : performanceData;
        optimizerData = data.optimizer && typeof data.optimizer === 'object' ? data.optimizer : optimizerData;
        reportData = data.report && typeof data.report === 'object' ? data.report : reportData;

        // Update Performance / Rehab Learning metadata (Version and Date range)
        const metaEl = document.getElementById('performance-metadata');
        if (metaEl) {
            const ver = data.strategy_version || '--';
            currentStrategyVersion = ver;
            let dateStr = '無歷史交易';
            if (data.journal_start && data.journal_end) {
                const formatTime = (ts) => {
                    const d = new Date(ts);
                    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
                };
                dateStr = `${formatTime(data.journal_start)} 至 ${formatTime(data.journal_end)}`;
            }
            metaEl.textContent = `機器人版本: ${ver} | 數據統計區間: ${dateStr}`;
        }

        refreshSessionMetrics();
        updateOverview();
        renderBotReport();
        renderEngineHeartbeat();
        renderModeCards();
        renderStrategyInfo();
        renderPerformance();
        renderTrades();
        renderRadar();
        
        // Render ML logs inside the Evolutionary Console with type safety
        const logConsole = document.getElementById('ml-log-console');
        if (logConsole && data.ml_logs && Array.isArray(data.ml_logs)) {
            logConsole.innerHTML = data.ml_logs.map(log => {
                const logStr = String(log || '');
                let color = '#e2e8f0';
                if (logStr.includes('康復期')) color = '#f87171';
                else if (logStr.includes('訓練中')) color = '#fbbf24';
                else if (logStr.includes('穩定獲利期')) color = '#34d399';
                return `<div style="color: ${color}; border-bottom: 1px solid rgba(255,255,255,0.02); padding: 4px 0;">${logStr}</div>`;
            }).join('');
            // Scroll to bottom
            logConsole.scrollTop = logConsole.scrollHeight;
        }
    } catch (error) {
        console.error('fetchTrades failed', error);
        showSyncError(error);
    }
}

async function fetchHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        historyData = Array.isArray(data.history) ? data.history : [];
        refreshSessionMetrics();
        renderHistory();
    } catch (error) {
        console.error('fetchHistory failed', error);
    }
}

async function fetchIntelligence() {
    try {
        const response = await fetch('/api/intelligence');
        const data = await response.json();
        profiles = data.profiles && typeof data.profiles === 'object' ? data.profiles : profiles;
        performanceData = data.performance && typeof data.performance === 'object' ? data.performance : performanceData;
        optimizerData = data.optimizer && typeof data.optimizer === 'object' ? data.optimizer : optimizerData;
        document.getElementById('intel-logic').textContent = '\u6bcf\u5c0f\u6642\u91cd\u65b0\u6311\u9078\u9ad8\u6d41\u52d5\u6027\u5e63\u7a2e\uff0c\u56db\u500b\u6a21\u5f0f\u5206\u5225\u6383\u63cf\uFF0C\u4ee5\u52dd\u7387\u8207 PF \u6c7a\u5b9a\u4fe1\u5fc3\u5009\u4f4d\u3002';
        const cloud = document.getElementById('intel-symbols');
        cloud.innerHTML = '';
        (data.symbols || []).slice(0, 40).forEach((symbol) => {
            const chip = document.createElement('span');
            chip.textContent = `${symbol} ${zhText(data.categories?.[symbol])}`;
            cloud.appendChild(chip);
        });
    } catch (error) {
        console.error('fetchIntelligence failed', error);
    }
}

document.querySelectorAll('.strat-btn').forEach((button) => {
    button.addEventListener('click', () => {
        document.querySelectorAll('.strat-btn').forEach((btn) => btn.classList.remove('active'));
        button.classList.add('active');
        currentStrategyFilter = button.dataset.strat;
        renderStrategyInfo();
        renderPerformance();
        renderTrades();
        renderRadar();
        renderHistory();
    });
});

document.querySelectorAll('.tab').forEach((tab) => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach((item) => item.classList.remove('active'));
        tab.classList.add('active');
        renderTrades();
    });
});

window.addEventListener('DOMContentLoaded', () => {
    fetchTrades();
    fetchHistory();
    fetchIntelligence();
    setInterval(fetchTrades, 5000);
    setInterval(fetchHistory, 30000);
    setInterval(fetchIntelligence, 60000);
});

// ═══════════════════════════════════════════════
// Engine Heartbeat Panel
// ═══════════════════════════════════════════════
const ENGINE_META = {
    MacroSniper:   { icon: '🎯', desc: '1H/4H \u8da8\u52e2\u72d9\u64ca', color: '#60a5fa' },
    MeanReversion: { icon: '↩️', desc: '\u5747\u503c\u56de\u6b78 RSI', color: '#a78bfa' },
    Contrarian:    { icon: '⚡', desc: '\u6975\u7aef\u53cd\u8f49\u7075\u9b42', color: '#f59e0b' },
    SqueezeHunter: { icon: '💥', desc: '\u64e0\u58d3\u7206\u767c\u8ddf\u8e64', color: '#34d399' },
};

function renderEngineHeartbeat() {
    const container = document.getElementById('engine-heartbeat');
    if (!container) return;

    // Count active trades per engine
    const engineActive = {};
    const enginePnl = {};
    currentTrades.filter(t => t.status === 'active').forEach(t => {
        let s = t.strategy || t.strategy_name || t.engine || 'Unknown';
        if (s === 'Unknown' || s === 'Recovered' || s === 'Manual') {
            const sym = String(t.symbol || '').toUpperCase();
            if (sym.includes('SOL')) s = 'MacroSniper';
            else if (sym.includes('SUI')) s = 'SqueezeHunter';
            else if (sym.includes('BTC')) s = 'MeanReversion';
            else if (sym.includes('ETH')) s = 'Contrarian';
            else s = 'MeanReversion';
        }
        engineActive[s] = (engineActive[s] || 0) + 1;
        enginePnl[s] = (enginePnl[s] || 0) + Number(t.pnl || 0);
    });

    // Count signals (potential) per engine
    const engineSignals = {};
    currentTrades.filter(t => t.status === 'potential').forEach(t => {
        const s = t.strategy || 'Unknown';
        engineSignals[s] = (engineSignals[s] || 0) + 1;
    });

    // Win rate from strategyStats
    const engines = ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'];
    container.innerHTML = engines.map(name => {
        const meta = ENGINE_META[name] || { icon: '•', desc: name, color: '#888' };
        const stats = sessionStrategyStats[name] || {};
        const perf = performanceData[name] || {};
        const opt = optimizerData[name] || {};
        const active = engineActive[name] || 0;
        const signals = engineSignals[name] || 0;
        const pnl = enginePnl[name] || 0;
        const wr = perf.win_rate != null ? perf.win_rate + '%' : '--';
        const conf = opt.capital_mult != null ? opt.capital_mult.toFixed(2) : (stats.confidence != null ? stats.confidence.toFixed(2) : '1.00');
        const verdict = perf.tier || 'D (Training/Explore)';
        const verdictColor = perf.state === 'exploit' ? '#22c55e' : perf.state === 'steady' ? '#60a5fa' : perf.state === 'pause' ? '#ef4444' : '#f59e0b';

        // Get detailed block reason from radarDict for this strategy
        const strategyRadar = radarData[name] || [];
        let detailedWaitingReason = '';
        
        // Check if frozen by market regime classifier
        if (latestRegime === 'trending' && ['MeanReversion', 'Contrarian'].includes(name)) {
            detailedWaitingReason = `<div style="color: #ef4444; font-size: 11px; margin-top: 4px;">🚫 大盤強趨勢：此模式已自動凍結防守</div>`;
        } else {
            // Get the block reason from the first item in radar queue
            const firstRadar = strategyRadar[0];
            if (firstRadar) {
                const reason = firstRadar.trigger_reason || firstRadar.block_reason || '掃描型態中 (Scanning)';
                detailedWaitingReason = `<div style="color: var(--muted); font-size: 10px; margin-top: 4px; border-left: 2px solid var(--line); padding-left: 4px;">⏳ 等待原因：${escapeHtml(zhReason(reason))} (${escapeHtml(firstRadar.symbol)})</div>`;
            } else {
                detailedWaitingReason = `<div style="color: var(--soft); font-size: 10px; margin-top: 4px;">⏳ 掃描中，目前無合適諧波區間</div>`;
            }
        }

        // Active trade stage summary
        const activeTrades = currentTrades.filter(t => {
            if (t.status !== 'active') return false;
            let s = t.strategy || t.strategy_name || t.engine || 'Unknown';
            if (s === 'Unknown' || s === 'Recovered' || s === 'Manual') {
                const sym = String(t.symbol || '').toUpperCase();
                if (sym.includes('SOL')) s = 'MacroSniper';
                else if (sym.includes('SUI')) s = 'SqueezeHunter';
                else if (sym.includes('BTC')) s = 'MeanReversion';
                else if (sym.includes('ETH')) s = 'Contrarian';
                else s = 'MeanReversion';
            }
            return s === name;
        });
        const stagesHtml = activeTrades.map(t => {
            const stage = t.trailing_stage;
            const stageTxt = stage === 'trailing' ? '奔跑' : stage === 'break_even' ? '保本' : '待觸發';
            const pnlNum = Number(t.pnl || 0);
            return `<div class="eng-trade"><span>${escapeHtml(t.symbol)}</span><span class="${pnlNum >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(pnlNum))}U [${escapeHtml(stageTxt)}]</span></div>`;
        }).join('');

        // Cumulative PnL from stats (Journal check)
        const cumPnl = Number(perf.total_pnl || 0);

        // Scanning status
        const scanStatus = signals > 0
            ? `<span class="eng-scanning">發現 ${signals} 個候選信號</span>`
            : `<span class="eng-idle">無信號 (監控中)</span>`;

        return `
        <div class="eng-card" style="border-top: 3px solid ${meta.color}">
            <div class="eng-head">
                <strong>${escapeHtml(meta.icon)} ${escapeHtml(strategyLabel(name))}</strong>
                <span class="eng-verdict" style="color:${verdictColor}">${escapeHtml(verdictLabel(verdict))}</span>
            </div>
            <div class="eng-desc">${escapeHtml(meta.desc)}</div>
            <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                <div><span>勝率</span><strong>${escapeHtml(wr)}</strong></div>
                <div><span>信心</span><strong>${escapeHtml(conf)}x</strong></div>
                <div><span>持倉</span><strong>${escapeHtml(active)} 張</strong></div>
                <div><span>浮盈</span><strong class="${pnl >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(pnl, 1))}U</strong></div>
                <div><span>累積盈虧</span><strong class="${cumPnl >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(cumPnl, 1))}U</strong></div>
            </div>
            <div class="eng-scan-status">${scanStatus}</div>
            ${detailedWaitingReason}
            ${stagesHtml ? '<div class="eng-trades">' + stagesHtml + '</div>' : ''}
        </div>`;
    }).join('');
}

// --- SECTION REMOVED TRIPLICATES ---

async function syncGithub() {
    const btn = document.getElementById('git-pull-btn');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.innerHTML = '<span>⏳ 正在同步 GitHub...</span>';

    try {
        const response = await fetch('/api/git-pull', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            alert(data.message);
            if (data.updated) {
                // 如果真的更新了，等待 3 秒讓 Flask 重啟完畢，然後自動刷新瀏覽器
                btn.innerHTML = '<span>🔄 機器人重啟中...</span>';
                setTimeout(() => {
                    location.reload();
                }, 3000);
                return;
            }
        } else {
            alert(`同步失敗: ${data.message || '未知錯誤'}`);
        }
    } catch (err) {
        alert(`無法連接到伺服器: ${err.message}`);
    } finally {
        if (btn && btn.disabled && btn.innerHTML !== '<span>🔄 機器人重啟中...</span>') {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = originalText;
        }
    }
}

async function resetOptimizer() {
    if (!confirm('確定要直接重製所有模式的自適應優化數值嗎？此操作將會清除當前優化器的歷史調整參數，使所有策略重置為基礎的「探索 (Explore)」狀態。')) {
        return;
    }

    const btn = document.getElementById('reset-opt-btn');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.innerHTML = '<span>⏳ 正在重製中...</span>';

    try {
        const response = await fetch('/api/reset-optimizer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();

        if (response.ok && data.success) {
            alert(data.message);
            location.reload();
        } else {
            alert(`重製失敗: ${data.message || '未知錯誤'}`);
        }
    } catch (err) {
        alert(`無法連接到伺服器: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = originalText;
        }
    }
}

