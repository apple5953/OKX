let currentTrades = [];
let historyData = [];
let radarData = {};
let profiles = {};
let strategyStats = {};
let performanceData = {};
let optimizerData = {};
let accountData = {};
let reportData = {};
let healthCheckData = {};
let entryEfficiencyData = {};
let uiMetricsData = {};
let marketRouterData = {};
let runtimeStatus = {};
let currentStrategyFilter = 'All';
let latestRegime = 'ranging';
let currentStrategyVersion = 'v13';
let dashboardSnapshotAt = '';
let dashboardCapital = {};
const DASHBOARD_SOURCES = Object.freeze({
    trades: '/api/trades',
    health: '/api/health-check',
});

let dashboardSourceState = {
    trades: DASHBOARD_SOURCES.trades,
    health: DASHBOARD_SOURCES.health,
    snapshotAt: '',
};

const START_EQUITY = 5000;
const TARGET_EQUITY = 10000;

function requestJson(path, options = {}) {
    const requestUrl = new URL(path, window.location.origin).toString();
    const requestOptions = {
        method: options.method || 'GET',
        headers: { ...(options.headers || {}) },
        body: options.body,
        cache: options.cache || 'no-store',
        credentials: options.credentials || 'same-origin',
    };

    if (typeof window.fetch === 'function') {
        return window.fetch(requestUrl, requestOptions);
    }

    return new Promise((resolve, reject) => {
        try {
            const xhr = new XMLHttpRequest();
            xhr.open(requestOptions.method, requestUrl, true);
            if (requestOptions.credentials === 'include') {
                xhr.withCredentials = true;
            }
            Object.entries(requestOptions.headers).forEach(([key, value]) => {
                xhr.setRequestHeader(key, String(value));
            });
            xhr.onreadystatechange = () => {
                if (xhr.readyState !== 4) return;
                resolve({
                    ok: xhr.status >= 200 && xhr.status < 300,
                    status: xhr.status,
                    async json() {
                        const raw = xhr.responseText || 'null';
                        try {
                            return JSON.parse(raw);
                        } catch {
                            return { raw };
                        }
                    },
                    async text() {
                        return xhr.responseText || '';
                    },
                    headers: {
                        get(name) {
                            return xhr.getResponseHeader(name);
                        },
                    },
                });
            };
            xhr.onerror = () => reject(new TypeError('Network request failed'));
            xhr.send(requestOptions.body ?? null);
        } catch (error) {
            reject(error);
        }
    });
}

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
    ['Monitoring active positions.', '監控實際持倉中。'],
    ['Protect at 0.25R, tighten near 0.55R, 移動止盈 winners, and keep orphan close orders under watch.', '先在 0.25R 保護，接近 0.55R 後收緊；贏家單採用移動止盈，並持續監看殘留的平倉單。'],
    ['Protect at 0.25R', '在 0.25R 時保護'],
    ['tighten near 0.55R', '接近 0.55R 時收緊'],
    ['keep orphan close orders under watch', '持續監看殘留的平倉單'],
    ['check required', '需要檢查'],
    ['winners', '贏家單'],
    [' and ', ' 與 '],
    ['移動止盈 贏家單, and 持續監看殘留的平倉單.', '移動止盈贏家單，並持續監看殘留的平倉單。'],
    ['Scanning', '掃描中'],
    ['scan', '掃描'],
    ['okx_account_balance', 'OKX 帳戶餘額'],
    ['okx_live_snapshot', 'OKX 即時快照'],
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
    if (raw.includes('Scanning')) return '\u6383\u63cf\u4e2d';
    if (raw.includes('PRZ breakout')) {
        const nearMatch = raw.match(/near\s+([0-9.eE+-]+)/);
        return nearMatch
            ? `PRZ \u7a81\u7834\u89c0\u5bdf\uff0c\u95dc\u9375\u50f9 ${nearMatch[1]}`
            : 'PRZ \u7a81\u7834\u89c0\u5bdf';
    }
    if (raw.includes('PRZ')) return '\u7b49\u5f85\u9032\u5165 PRZ \u5340\u57df / \u5c1a\u672a\u5f62\u6210\u958b\u55ae\u9ede';
    if (raw.startsWith('training rehab waiting: needs RR >=')) {
        return raw
            .replace('training rehab waiting: needs RR >=', '\u8a13\u7df4\u689d\u4ef6\u672a\u9054\u6a19\uff1a\u9700\u8981 RR >=')
            .replace('and profit room >=', '\uff0c\u5229\u6f64\u7a7a\u9593 >=');
    }
    const item = reasonMap.find(([key]) => raw.includes(key));
    const normalized = item ? item[1] : zhText(raw)
        .replace('margin', '\u4fdd\u8b49\u91d1')
        .replace('at', '\u69d3\u687f');
    if (/[?銝]/.test(normalized)) return '掃描中';
    return normalized;
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
    const exchangeVerified = trade?.exchange_protection_verified === true || String(trade?.exchange_protection_verified || '').toLowerCase() === 'true';

    if (protectionLooksAlreadyClosed(trade)) {
        return '保護單未回報，但倉位已不存在';
    }
    if (status === 'confirmed' && !exchangeVerified && trade?.status === 'active') {
        return 'OKX 保護單未驗證';
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

function runtimeLabel(mode) {
    const raw = String(mode || '').toLowerCase();
    if (raw === 'mock') return '\u6a21\u64ec\u55ae';
    if (raw === 'live') return '\u5be6\u76e4';
    return '\u81ea\u52d5';
}

function optimizerLine(opt) {
    if (!opt) return '\u81ea\u52d5\u8abf\u53c3\u5c1a\u672a\u540c\u6b65';
    return `\u81ea\u52d5\u8abf\u53c3: ${optimizerLabel(opt)} / \u9032\u5834x${num(opt.tolerance_mult, 2)} / RRx${num(opt.target_rr_mult, 2)} / \u51b7\u537bx${num(opt.cooldown_mult, 2)}`;
}

function sourceLabelText(source, snapshotAt = '') {
    const label = String(source || '-').trim();
    const snapshot = snapshotAt ? `｜${snapshotAt}` : '';
    return `來源：${label}${snapshot}`;
}

function setTextIfExists(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setMetricSource(id, value) {
    const target = document.getElementById(id);
    if (!target) return;
    const text = value || '來源：-';
    let sourceEl = target.nextElementSibling;
    if (!sourceEl || !sourceEl.classList || !sourceEl.classList.contains('metric-source')) {
        sourceEl = document.createElement('small');
        sourceEl.className = 'metric-source';
        target.insertAdjacentElement('afterend', sourceEl);
    }
    sourceEl.textContent = text;
    sourceEl.title = text;
}

function setSourceBadge(id, source, snapshotAt = '', title = '') {
    const el = document.getElementById(id);
    if (!el) return;
    const label = sourceLabelText(source, snapshotAt);
    el.textContent = label;
    el.title = title || label;
}

function refreshSourceBadges() {
    const snapshotAt = dashboardSourceState.snapshotAt || dashboardSnapshotAt || reportData?.server_time || healthCheckData?.generated_at || '-';
    const liveTitle = `來源：OKX / 活倉快照｜${DASHBOARD_SOURCES.trades}｜${snapshotAt}`;
    const healthTitle = `來源：OKX / 健康檢查｜${DASHBOARD_SOURCES.health}｜${snapshotAt}`;
    const ensureBadge = ({ sectionTitle, badgeId, source, title }) => {
        const section = Array.from(document.querySelectorAll('section')).find((item) => {
            const heading = item.querySelector('.panel-head h2');
            return heading && heading.textContent.trim() === sectionTitle;
        });
        if (!section) return;
        const head = section.querySelector('.panel-head');
        if (!head) return;
        let badge = document.getElementById(badgeId);
        if (!badge || badge.parentElement !== head) {
            if (badge && badge.parentElement) {
                badge.remove();
            }
            badge = document.createElement('span');
            badge.id = badgeId;
            badge.className = 'source-pill';
            head.appendChild(badge);
        }
        setSourceBadge(badgeId, source, snapshotAt, title);
    };
    [
        { sectionTitle: '引擎即時狀態', badgeId: 'engine-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
        { sectionTitle: '機器人即時報告', badgeId: 'report-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
        { sectionTitle: 'V13 健康檢查', badgeId: 'health-source', source: DASHBOARD_SOURCES.health, title: healthTitle },
        { sectionTitle: '模式控制台', badgeId: 'modes-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
        { sectionTitle: '盈利驗證 / 復健學習', badgeId: 'performance-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
        { sectionTitle: '目前倉位', badgeId: 'trades-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
        { sectionTitle: '市場雷達', badgeId: 'radar-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
        { sectionTitle: '已平倉紀錄', badgeId: 'history-source', source: DASHBOARD_SOURCES.trades, title: liveTitle },
    ].forEach(ensureBadge);
}

function modeTierLabel(tier) {
    if (tier === 'live_core') return '核心實戰';
    if (tier === 'live_calibration') return '校準實戰';
    return '觀察中';
}

function getUnifiedReportModes() {
    const liveModes = Array.isArray(reportData?.live_modes) ? reportData.live_modes : [];
    const weakModes = Array.isArray(reportData?.weak_modes) ? reportData.weak_modes : [];
    return { liveModes, weakModes };
}

function getUnifiedReportMetrics() {
    const capital = accountData.capital || {};
    const activeTrades = currentTrades.filter((trade) => trade.status === 'active');
    const potentialTrades = currentTrades.filter((trade) => trade.status === 'potential');
    const report = reportData && typeof reportData === 'object' ? reportData : {};
    const capitalUnrealized = Number(
        capital.strategy_unrealized ??
        report.active_pnl ??
        activeTrades.reduce((sum, trade) => sum + Number(trade.pnl || 0), 0)
    );
    return {
        activeCount: Number(report.active_count ?? activeTrades.length ?? 0),
        potentialCount: Number(report.potential_count ?? potentialTrades.length ?? 0),
        activePnl: capitalUnrealized,
        sessionActiveCount: Number(report.session_active_count ?? 0),
        sessionPotentialCount: Number(report.session_potential_count ?? 0),
        sessionActivePnl: Number(report.session_active_pnl ?? 0),
        sessionRealizedPnl: Number(report.session_realized_pnl ?? 0),
        activePnlSource: capital.strategy_unrealized_source || report.active_pnl_source || 'OKX / 活倉快照',
        sessionActiveSource: report.session_active_pnl_source || 'OKX / 活倉快照',
        sessionRealizedSource: report.session_realized_pnl_source || '已驗證歷史 / session alphaPnl',
        verdict: report.verdict || '掃描中',
        protectionRule: report.protection_rule || '-',
        serverTime: report.server_time || '-',
        positions: Array.isArray(report.positions) ? report.positions : [],
        trackedPositions: Array.isArray(report.tracked_positions) ? report.tracked_positions : [],
        capital,
        capitalSource: capital.cumulative_source || capital.pnl_source || 'OKX / 帳戶快照',
    };
}

function renderRuntimeStatus() {
    const chip = document.getElementById('runtime-wrapper');
    const textEl = document.getElementById('runtime-text');
    if (!chip || !textEl) return;

    const mode = String(runtimeStatus.run_mode || (runtimeStatus.mock_mode ? 'mock' : 'auto')).toLowerCase();
    const label = runtimeStatus.label || runtimeLabel(mode);
    const nodeName = runtimeStatus.node_name || '-';
    const creds = runtimeStatus.credentials_ready ? '\u5df2\u8a2d\u5b9a\u6a5f\u69cb' : '\u5c1a\u672a\u8a2d\u5b9a\u6a5f\u69cb';
    const detail = runtimeStatus.detail || '';

    textEl.textContent = `${label}｜${nodeName}｜${creds}`;
    chip.title = detail || `${label} ${nodeName}`;

    if (mode === 'mock') {
        chip.style.background = 'rgba(34,197,94,0.15)';
        chip.style.border = '1px solid rgba(34,197,94,0.3)';
        chip.style.color = '#22c55e';
    } else if (mode === 'live') {
        chip.style.background = 'rgba(248,113,113,0.15)';
        chip.style.border = '1px solid rgba(248,113,113,0.3)';
        chip.style.color = '#f87171';
    } else {
        chip.style.background = 'rgba(245,158,11,0.15)';
        chip.style.border = '1px solid rgba(245,158,11,0.3)';
        chip.style.color = '#f59e0b';
    }
}

function renderRuntimeStatusV2() {
    const chip = document.getElementById('runtime-wrapper');
    const textEl = document.getElementById('runtime-text');
    if (!chip || !textEl) return;

    const mode = String(runtimeStatus.run_mode || (runtimeStatus.mock_mode ? 'mock' : 'auto')).toLowerCase();
    const label = runtimeStatus.label || runtimeLabel(mode);
    const nodeName = runtimeStatus.node_name || '-';
    const creds = runtimeStatus.credentials_ready ? 'API已設定' : 'API未設定';
    const summary = runtimeStatus.summary || `${label}｜${nodeName}｜${creds}`;
    const detail = runtimeStatus.detail || '';

    textEl.textContent = summary;
    chip.title = detail || summary;

    if (mode === 'mock') {
        chip.style.background = 'rgba(34,197,94,0.15)';
        chip.style.border = '1px solid rgba(34,197,94,0.3)';
        chip.style.color = '#22c55e';
    } else if (mode === 'live') {
        chip.style.background = 'rgba(248,113,113,0.15)';
        chip.style.border = '1px solid rgba(248,113,113,0.3)';
        chip.style.color = '#f87171';
    } else {
        chip.style.background = 'rgba(245,158,11,0.15)';
        chip.style.border = '1px solid rgba(245,158,11,0.3)';
        chip.style.color = '#f59e0b';
    }
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
    const rows = Array.isArray(source) ? source : [];
    if (currentStrategyFilter === 'All') return rows;
    return rows.filter((item) => {
        const strat = rowStrategyName(item);
        return strat === currentStrategyFilter || normalizedEngineBucket(item) === currentStrategyFilter;
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

function normalizedEngineBucket(item) {
    let name = rowStrategyName(item);
    if (['Unknown', 'Recovered', 'Manual', 'Bot', 'Mixed', 'Machine'].includes(name)) {
        const sym = String(item?.symbol || '').toUpperCase();
        if (sym.includes('SOL')) name = 'MacroSniper';
        else if (sym.includes('SUI')) name = 'SqueezeHunter';
        else if (sym.includes('BTC')) name = 'MeanReversion';
        else if (sym.includes('ETH')) name = 'Contrarian';
        else name = 'MeanReversion';
    }
    return name;
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
    return (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade.status === 'active' && isSessionRow(trade));
}

function sessionPotentialTrades() {
    return (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade.status === 'potential' && isSessionRow(trade));
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

function deprecatedUpdateProgressCurve(pnlVal, signedProgress) {
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
    const verTag = match ? match[0].toUpperCase() : 'V13';
    const pnlText = `${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)} USDT`;
    const pctText = `${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%`;

    document.getElementById('curve-label').textContent = `${verTag} 累積盈虧 ${pnlText} (${pctText})`;
    document.getElementById('curve-label').setAttribute('x', Math.max(60, Math.min(520, x - 28)));
    document.getElementById('curve-label').setAttribute('y', isDrawdown ? 174 : 28);
    const capitalStart = Number(dashboardCapital.start ?? START_EQUITY);
    const capitalTarget = Number(dashboardCapital.target ?? TARGET_EQUITY);
    const startLabel = document.getElementById('progress-start-label');
    const targetLabel = document.getElementById('progress-target-label');
    const titleLabel = document.getElementById('growth-title');
    if (startLabel) startLabel.textContent = `${money(capitalStart)} USDT`;
    if (targetLabel) targetLabel.textContent = `${money(capitalTarget)} USDT`;
    if (titleLabel) titleLabel.textContent = `${verTag} 帳戶成長進度`;
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

function healthStatusLabel(status) {
    if (status === 'critical') return '嚴重異常';
    if (status === 'warning') return '需注意';
    return '正常';
}

function healthStatusClass(status) {
    if (status === 'critical') return 'critical';
    if (status === 'warning') return 'warning';
    return 'good';
}

function renderHealthList(items, emptyLabel) {
    if (!Array.isArray(items) || !items.length) {
        return `<div class="health-item good"><strong>OK</strong><small>${escapeHtml(emptyLabel)}</small></div>`;
    }
    return items.map((item) => {
        const titleParts = [item.symbol, item.strategy].filter(Boolean);
        const title = titleParts.length ? titleParts.join(' / ') : 'unknown';
        const meta = [
            item.accounting_status ? `acct:${item.accounting_status}` : '',
            item.protection_status ? `prot:${item.protection_status}` : '',
            item.trailing_stage ? `stage:${item.trailing_stage}` : '',
            item.source ? `src:${item.source}` : '',
        ].filter(Boolean).join(' | ');
        const reasons = Array.isArray(item.reasons) ? item.reasons.join(' | ') : String(item.reasons || '');
        const klass = item.category || item.severity || 'warning';
        return `
            <div class="health-item ${escapeHtml(klass)}">
                <strong>${escapeHtml(title)}</strong>
                <small>${escapeHtml(meta)}</small>
                <small>${escapeHtml(reasons)}</small>
            </div>
        `;
    }).join('');
}

function buildHealthCheckModel() {
    const data = healthCheckData || {};
    const counts = data.counts || {};
    const liveCounts = {
        activeTrades: Number(counts.active_trades || 0),
        badTrades: Number(counts.bad_trades || 0),
        protectionWarnings: Number(counts.protection_warnings || 0),
        trainingIssues: Number(counts.training_issues || 0),
    };
    const sessionCounts = {
        activeTrades: Number(counts.session_active_trades ?? 0),
        potentialTrades: Number(counts.session_potential_trades ?? 0),
        trainingIssues: Number(counts.session_training_issues ?? 0),
    };
    return { data, counts, liveCounts, sessionCounts };
}

function deprecatedRenderHealthCheck() {
    const summary = document.getElementById('health-summary');
    const blocks = document.getElementById('health-blocks');
    const detail = document.getElementById('health-detail');
    const stateEl = document.getElementById('health-check-state');
    if (!summary || !blocks || !detail || !stateEl) return;

    const model = buildHealthCheckModel();
    const data = model.data;
    const counts = model.counts;
    const liveCounts = model.liveCounts;
    const sessionCounts = model.sessionCounts;
    const status = String(data.status || 'warning').toLowerCase();
    const score = Number(data.score);
    const runtime = data.runtime || {};
    const version = data.strategy_version || currentStrategyVersion || 'v13';
    const zeroStart = data.zero_start || {};
    const snapshotAt = data.snapshot_at || data.generated_at || dashboardSnapshotAt || '-';

    stateEl.textContent = `${healthStatusLabel(status)} / 分數 ${Number.isFinite(score) ? score.toFixed(0) : '-'}`;
    summary.innerHTML = `
        <div class="health-card">
            <span>狀態</span>
            <strong class="${healthStatusClass(status)}">${healthStatusLabel(status)}</strong>
            <small>${escapeHtml(zhText(data.health_summary?.message || '已就緒'))}</small>
        </div>
        <div class="health-card">
            <span>健康分數</span>
            <strong class="${healthStatusClass(status)}">${Number.isFinite(score) ? score.toFixed(0) : '-'}</strong>
            <small>版本 ${escapeHtml(version)}</small>
        </div>
        <div class="health-card">
            <span>壞單數</span>
            <strong class="${counts.bad_trades > 0 ? 'loss' : 'gain'}">${counts.bad_trades ?? 0}</strong>
            <small>${counts.active_trades ?? 0} 個持倉 / ${counts.protection_warnings ?? 0} 個警告</small>
        </div>
        <div class="health-card">
            <span>訓練異常</span>
            <strong class="${counts.training_issues > 0 ? 'loss' : 'gain'}">${counts.training_issues ?? 0}</strong>
            <small>${counts.quarantined_rows ?? 0} 筆隔離 / ${counts.version_mismatch_rows ?? 0} 筆版本不符</small>
        </div>
    `;

    const summaryCards = summary.querySelectorAll('.health-card');
    if (summaryCards[2]) {
        summaryCards[2].innerHTML = `
            <span>實盤執行</span>
            <strong class="${liveCounts.badTrades > 0 ? 'loss' : 'gain'}">${liveCounts.badTrades}</strong>
            <small>${liveCounts.activeTrades} 個持倉 / ${counts.protection_warnings ?? 0} 個警告</small>
        `;
    }
    if (summaryCards[3]) {
        summaryCards[3].innerHTML = `
            <span>訓練 / Session</span>
            <strong class="${sessionCounts.trainingIssues > 0 ? 'loss' : 'gain'}">${sessionCounts.trainingIssues}</strong>
            <small>${sessionCounts.activeTrades} 個實際 / ${sessionCounts.potentialTrades} 個候選</small>
        `;
    }

    blocks.innerHTML = `
        <div class="health-block">
            <div class="health-block-title">
                <strong>壞單清單</strong>
                <span>${counts.bad_trades ?? 0} 筆</span>
            </div>
            <div class="health-list">
                ${renderHealthList(data.bad_trades || [], '目前沒有壞單')}
            </div>
        </div>
        <div class="health-block">
            <div class="health-block-title">
                <strong>保護警告</strong>
                <span>${counts.protection_warnings ?? 0} 筆</span>
            </div>
            <div class="health-list">
                ${renderHealthList(data.protection_warnings || [], '目前沒有保護警告')}
            </div>
        </div>
    `;

    detail.innerHTML = `
        <div class="health-detail-card">
            <h3>異常訓練資料</h3>
            <span class="hint">包含隔離、版本不符、或不適合訓練的資料列。</span>
            <div class="health-tags">
                <span class="health-tag ${healthStatusClass(status)}">${healthStatusLabel(status)}</span>
                <span class="health-tag">已驗證 ${counts.verified_rows ?? 0}</span>
                <span class="health-tag ${counts.training_issues > 0 ? 'warning' : 'good'}">異常 ${counts.training_issues ?? 0}</span>
            </div>
            <div class="health-list">
                ${renderHealthList(data.abnormal_training_rows || [], '目前沒有異常訓練資料')}
            </div>
        </div>
        <div class="health-detail-card">
            <h3>系統快照</h3>
            <span class="hint">${escapeHtml(version)} / ${escapeHtml(snapshotAt)}</span>
            <div class="health-tags">
                <span class="health-tag ${runtime.run_mode === 'live' ? 'critical' : (runtime.run_mode === 'demo' ? 'warning' : 'good')}">${escapeHtml(runtime.run_mode === 'live' ? '實盤' : runtime.run_mode === 'demo' ? '模擬' : '自動')}</span>
                <span class="health-tag">節點 ${escapeHtml(runtime.node_name || '-')}</span>
                <span class="health-tag">持倉 ${counts.active_trades ?? 0}</span>
                <span class="health-tag ${zeroStart.zero_start_mode ? 'good' : 'warning'}">零起點 ${zeroStart.zero_start_mode ? '啟用' : '關閉'}</span>
            </div>
            <span class="hint">${escapeHtml(zhText(data.health_summary?.message || '沒有其他備註'))}</span>
        </div>
    `;
    const detailCards = detail.querySelectorAll('.health-detail-card');
    if (detailCards[0]) {
        detailCards[0].querySelector('.health-tags').innerHTML = `
            <span class="health-tag ${healthStatusClass(status)}">${healthStatusLabel(status)}</span>
            <span class="health-tag">已驗證 ${counts.verified_rows ?? 0}</span>
            <span class="health-tag ${sessionCounts.trainingIssues > 0 ? 'warning' : 'good'}">Session 異常 ${sessionCounts.trainingIssues}</span>
        `;
    }
    if (detailCards[1]) {
        detailCards[1].querySelector('.health-tags').innerHTML = `
            <span class="health-tag ${runtime.run_mode === 'live' ? 'critical' : (runtime.run_mode === 'demo' ? 'warning' : 'good')}">${escapeHtml(runtime.run_mode === 'live' ? '撖衣' : runtime.run_mode === 'demo' ? '璅⊥' : '?芸?')}</span>
            <span class="health-tag">節點 ${escapeHtml(runtime.node_name || '-')}</span>
            <span class="health-tag">實盤 ${liveCounts.activeTrades}</span>
            <span class="health-tag">Session ${sessionCounts.activeTrades}/${sessionCounts.potentialTrades}</span>
            <span class="health-tag ${zeroStart.zero_start_mode ? 'good' : 'warning'}">零起點 ${zeroStart.zero_start_mode ? '啟用' : '關閉'}</span>
        `;
    }
}

async function fetchHealthCheck() {
    const stateEl = document.getElementById('health-check-state');
    if (stateEl) stateEl.textContent = '重新整理中...';
    try {
        const response = await requestJson('/api/health-check', { cache: 'no-store' });
        if (!response.ok) throw new Error(`API ${response.status}`);
        const data = await response.json();
        healthCheckData = data && typeof data === 'object' ? data : {};
        dashboardSourceState.snapshotAt = dashboardSourceState.snapshotAt || healthCheckData.generated_at || dashboardSnapshotAt || '';
        renderHealthCheck();
        refreshSourceBadges();
    } catch (error) {
        console.error('fetchHealthCheck failed', error);
        if (stateEl) stateEl.textContent = '健康檢查失敗';
        const summary = document.getElementById('health-summary');
        const blocks = document.getElementById('health-blocks');
        const detail = document.getElementById('health-detail');
        if (summary) {
            summary.innerHTML = `
                <div class="health-card">
                    <span>狀態</span>
                    <strong class="loss">錯誤</strong>
                    <small>${escapeHtml(error?.message || '健康檢查失敗')}</small>
                </div>
            `;
        }
        if (blocks) {
            blocks.innerHTML = `
                <div class="health-block">
                    <div class="health-block-title"><strong>壞單清單</strong><span>0 筆</span></div>
                    <div class="health-list"><div class="health-item critical"><strong>API 錯誤</strong><small>${escapeHtml(error?.message || '無法載入健康檢查資料')}</small></div></div>
                </div>
            `;
        }
        if (detail) {
            detail.innerHTML = `
                <div class="health-detail-card">
                    <h3>系統快照</h3>
                    <span class="hint">API 錯誤</span>
                </div>
            `;
        }
    }
}

function deprecatedRenderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const { liveModes, weakModes } = getUnifiedReportModes();
    const metrics = getUnifiedReportMetrics();
    const positions = metrics.positions;
    const trackedPositions = metrics.trackedPositions;
    const positionSource = positions.length ? 'OKX 實際持倉' : 'OKX 訓練持倉';

    const liveText = liveModes.length
        ? liveModes.map((m) => `${escapeHtml(strategyLabel(m.strategy))} ${escapeHtml(modeTierLabel(m.tier))} / PF ${escapeHtml(num(m.pf, 3))} / 保證金 ${escapeHtml(money(m.max_margin))}`).join('<br>')
        : '目前沒有核心實戰模式';
    const weakText = weakModes.length
        ? weakModes.map((m) => `${escapeHtml(strategyLabel(m.strategy))} ${escapeHtml(modeTierLabel(m.tier))} / PF ${escapeHtml(num(m.pf, 3))} / 保證金 ${escapeHtml(money(m.max_margin))}`).join('<br>')
        : '目前沒有弱勢模式';
    const positionText = positions.length
        ? positions.map((p) => `${escapeHtml(positionSource)} · ${escapeHtml(p.symbol)} ${escapeHtml(directionLabel(p.direction))} 入場 ${escapeHtml(num(p.entry))} / 現價 ${escapeHtml(num(p.current))} / PnL ${escapeHtml(signed(p.pnl))} / ${escapeHtml(zhText(p.stage))}`).join('<br>')
        : (trackedPositions.length ? '目前只有訓練持倉，尚無 OKX 實際持倉' : '目前沒有持倉');

    box.innerHTML = `
        <div class="report-main">
            <div><span>目前結論</span><strong>${escapeHtml(zhText(metrics.verdict || '-'))}</strong><small>${escapeHtml(metrics.serverTime || '-')}</small></div>
            <div><span>實際 / 候選</span><strong>${escapeHtml(metrics.activeCount)} / ${escapeHtml(metrics.potentialCount)}</strong><small>浮動 ${escapeHtml(signed(metrics.activePnl))} / 會話 ${escapeHtml(signed(metrics.sessionActivePnl))}</small></div>
            <div><span>出場保護</span><strong>MFE</strong><small>${escapeHtml(zhText(metrics.protectionRule || '-'))}</small></div>
        </div>
        <div class="report-lines">
            <div><span>核心模式</span><p>${liveText}</p></div>
            <div><span>觀察模式</span><p>${weakText}</p></div>
            <div><span>持倉明細</span><p>${positionText}</p></div>
        </div>
    `;
}

function getUnifiedReportMetrics() {
    const capital = accountData.capital || {};
    const activeTrades = currentTrades.filter((trade) => trade.status === 'active');
    const potentialTrades = currentTrades.filter((trade) => trade.status === 'potential');
    const report = reportData && typeof reportData === 'object' ? reportData : {};
    const capitalUnrealized = Number(
        capital.strategy_unrealized ??
        report.active_pnl ??
        activeTrades.reduce((sum, trade) => sum + Number(trade.pnl || 0), 0)
    );
    const capitalSnapshotAvailable = Boolean(capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    return {
        activeCount: Number(report.active_count ?? activeTrades.length ?? 0),
        potentialCount: Number(report.potential_count ?? potentialTrades.length ?? 0),
        activePnl: capitalUnrealized,
        sessionActiveCount: Number(report.session_active_count ?? 0),
        sessionPotentialCount: Number(report.session_potential_count ?? 0),
        sessionActivePnl: Number(report.session_active_pnl ?? 0),
        sessionRealizedPnl: Number(report.session_realized_pnl ?? 0),
        activePnlSource: capital.strategy_unrealized_source || report.active_pnl_source || 'OKX / 活倉快照',
        sessionActiveSource: report.session_active_pnl_source || 'OKX / 活倉快照',
        sessionRealizedSource: report.session_realized_pnl_source || '已驗證歷史 / session alphaPnl',
        verdict: report.verdict || '觀察中',
        protectionRule: report.protection_rule || '-',
        serverTime: report.server_time || '-',
        positions: Array.isArray(report.positions) ? report.positions : [],
        trackedPositions: Array.isArray(report.tracked_positions) ? report.tracked_positions : [],
        capital,
        capitalSnapshotAvailable,
        capitalSource: capital.account_layer_source || capital.cumulative_source || capital.pnl_source || (capitalSnapshotAvailable ? 'OKX / 帳戶快照' : '帳戶快照不可用 / Session 推算'),
    };
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalSnapshotAvailable = Boolean(metrics.capitalSnapshotAvailable ?? capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    const capitalPnl = capitalSnapshotAvailable
        ? Number(capital.account_layer_pnl ?? capital.cumulative_pnl ?? 0)
        : null;
    const sessionPnl = Number(capital.session_cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.account_layer_source || capital.cumulative_source || 'OKX / 帳戶快照';

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        if (capitalPnl == null || !Number.isFinite(capitalPnl)) {
            capitalChangeEl.textContent = '--';
            capitalChangeEl.className = 'value';
            capitalChangeEl.title = 'OKX 帳戶快照不可用，未以策略推算值冒充帳戶層';
        } else {
            capitalChangeEl.textContent = `${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)}`;
            capitalChangeEl.className = capitalPnl >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = `帳戶層來源：${capitalSource}`;
        }
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧（帳戶層）' : 'V13 累積盈虧（帳戶快照不可用）';
    setMetricSource('capital-change', capitalSnapshotAvailable ? `來源：${capitalSource}` : '來源：OKX 帳戶快照不可用 / 只顯示 Session 推算');

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (sessionPnl / targetProfitGoal) * 100 : 0);
    const curvePnl = capitalSnapshotAvailable ? Number(capitalPnl ?? 0) : sessionPnl;
    updateProgressCurve(curvePnl, signedProgress);
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧曲線（帳戶層）' : 'V13 Session 推算曲線（非帳戶層）';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }
}

function renderHistory() {
    const tbody = document.getElementById('history-body');
    const summary = document.getElementById('history-summary');
    tbody.innerHTML = '';
    const rows = filtered(historyData).slice(0, 80);
    const closedTradeTotalPnl = rows.reduce((sum, item) => {
        const info = item.info || {};
        return sum + Number(item.realizedPnl || info.realizedPnl || 0);
    }, 0);

    if (summary) {
        summary.innerHTML = `
            <div class="summary-card">
                <span>已平倉筆數</span>
                <strong>${rows.length}</strong>
            </div>
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${closedTradeTotalPnl >= 0 ? 'gain' : 'loss'}">${signed(closedTradeTotalPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>本頁口徑</span>
                <strong>只看 closed trades</strong>
            </div>
        `;
    }

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
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl, 4)}<small>手續費 ${signed(fee, 4)} / 資金費 ${signed(funding, 4)}</small></td>
            <td>${item.timestamp ? new Date(item.timestamp).toLocaleString() : '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;

    const { liveModes, weakModes } = getUnifiedReportModes();
    const metrics = getUnifiedReportMetrics();
    const positions = Array.isArray(metrics.positions) ? metrics.positions : [];
    const trackedPositions = Array.isArray(metrics.trackedPositions) ? metrics.trackedPositions : [];
    const activeCount = Number(metrics.activeCount || 0);
    const potentialCount = Number(metrics.potentialCount || 0);
    const activePnl = Number(metrics.activePnl || 0);
    const sessionActivePnl = Number(metrics.sessionActivePnl || 0);
    const sessionRealizedPnl = Number(metrics.sessionRealizedPnl || 0);
    const verdict = zhText(metrics.verdict || '-');
    const serverTime = metrics.serverTime || '-';

    box.innerHTML = `
        <div class="health-summary">
            <div class="health-card">
                <span>即時狀態</span>
                <strong class="${activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(verdict)}</strong>
                <small>${escapeHtml(serverTime)}</small>
            </div>
            <div class="health-card">
                <span>即時持倉</span>
                <strong class="${activePnl >= 0 ? 'gain' : 'loss'}">${signed(activePnl)}</strong>
                <small>${activeCount} 個持倉 / ${potentialCount} 個候選</small>
            </div>
            <div class="health-card">
                <span>執行狀態</span>
                <strong class="${trackedPositions.length > 0 ? 'warning' : 'good'}">${trackedPositions.length} 筆追蹤</strong>
                <small>Session ${signed(sessionActivePnl)} / 已實現 ${signed(sessionRealizedPnl)}</small>
            </div>
            <div class="health-card">
                <span>模式統計</span>
                <strong class="${liveModes.length > 0 ? 'gain' : 'loss'}">${liveModes.length} / ${weakModes.length}</strong>
                <small>實戰 / 觀察</small>
            </div>
        </div>
        <div class="health-blocks">
            <div class="health-block">
                <div class="health-block-title">
                    <strong>即時持倉</strong>
                    <span>${positions.length} 筆</span>
                </div>
                <div class="health-list">
                    ${renderHealthList(positions.map((p) => ({
                        symbol: p.symbol,
                        strategy: p.strategy,
                        source: p.source,
                        status: p.status,
                        category: Number(p.pnl || 0) >= 0 ? 'good' : 'warning',
                        reasons: [
                            `${directionLabel(p.direction)} / ${num(p.entry)} → ${num(p.current)}`,
                            `PnL ${signed(p.pnl)}`,
                            zhText(p.stage),
                        ],
                    })), '即時持倉')}
                </div>
            </div>
            <div class="health-block">
                <div class="health-block-title">
                    <strong>模式分配</strong>
                    <span>${liveModes.length + weakModes.length} 種</span>
                </div>
                <div class="health-list">
                    ${renderHealthList([
                        ...liveModes.map((m) => ({
                            symbol: strategyLabel(m.strategy),
                            strategy: m.strategy,
                            category: 'good',
                            reasons: [`${modeTierLabel(m.tier)}`, `PF ${num(m.pf, 3)}`, `Margin ${money(m.max_margin)}`],
                        })),
                        ...weakModes.map((m) => ({
                            symbol: strategyLabel(m.strategy),
                            strategy: m.strategy,
                            category: 'warning',
                            reasons: [`${modeTierLabel(m.tier)}`, `PF ${num(m.pf, 3)}`, `Margin ${money(m.max_margin)}`],
                        })),
                    ], '模式分配')}
                </div>
            </div>
        </div>
        <div class="health-detail-grid">
            <div class="health-detail-card">
                <h3>即時狀態</h3>
                <span class="hint">同一份快照下的持倉與執行方向</span>
                <div class="health-tags">
                    <span class="health-tag ${activeCount > 0 ? 'warning' : 'good'}">持倉 ${activeCount}</span>
                    <span class="health-tag">候選 ${potentialCount}</span>
                    <span class="health-tag ${activePnl >= 0 ? 'good' : 'warning'}">浮盈 ${signed(activePnl)}</span>
                    <span class="health-tag">快照 ${escapeHtml(serverTime)}</span>
                </div>
                <div class="health-list">
                    ${renderHealthList(positions, '即時持倉')}
                </div>
            </div>
            <div class="health-detail-card">
                <h3>訓練統計</h3>
                <span class="hint">模式分配與 session 計算</span>
                <div class="health-tags">
                    <span class="health-tag ${liveModes.length > 0 ? 'good' : 'warning'}">實戰 ${liveModes.length}</span>
                    <span class="health-tag ${weakModes.length > 0 ? 'warning' : 'good'}">觀察 ${weakModes.length}</span>
                    <span class="health-tag">Session ${signed(sessionActivePnl)}</span>
                    <span class="health-tag">已實現 ${signed(sessionRealizedPnl)}</span>
                </div>
                <div class="health-list">
                    ${renderHealthList([
                        ...liveModes.map((m) => ({
                            symbol: strategyLabel(m.strategy),
                            strategy: m.strategy,
                            category: 'good',
                            reasons: [`${modeTierLabel(m.tier)}`, `PF ${num(m.pf, 3)}`, `Margin ${money(m.max_margin)}`],
                        })),
                        ...weakModes.map((m) => ({
                            symbol: strategyLabel(m.strategy),
                            strategy: m.strategy,
                            category: 'warning',
                            reasons: [`${modeTierLabel(m.tier)}`, `PF ${num(m.pf, 3)}`, `Margin ${money(m.max_margin)}`],
                        })),
                    ], '模式統計')}
                </div>
            </div>
        </div>
    `;
}

// FINAL V13 canonical overrides. These must stay last because this file still
// contains legacy duplicate renderers above.
function getUnifiedReportMetrics() {
    const snap = v13Snapshot();
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
}

function buildStrategyCardModel(name) {
    const { liveModes, weakModes } = getUnifiedReportModes();
    const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
    const reportMode = reportModes.get(name) || {};
    const stats = strategyStats[name] || {};
    const perf = performanceData[name] || {};
    const opt = optimizerData[name] || {};
    const liveTrades = v13TradesForMode(name, 'active');
    const candidateTrades = v13TradesForMode(name, 'potential');
    const livePnl = liveTrades.reduce((sum, trade) => sum + v13Num(trade.pnl, 0), 0);
    const cumulativePnl = v13ModeRealizedPnl(name);
    const sample = v13Num(perf.sample ?? perf.total_trades, 0);
    return {
        reportMode,
        stats,
        perf,
        opt,
        liveTrades,
        candidateTrades,
        livePnl,
        cumulativePnl,
        cumulativePnlSource: '來源：同一快照 performance.total_pnl',
        winRate: (perf.win_rate == null || sample === 0) ? '-' : pct(perf.win_rate, 1),
        verdict: perf.verdict || stats.verdict || 'learning',
        tierLabel: reportMode.tier ? modeTierLabel(reportMode.tier) : modeTierLabel(opt.state === 'exploit' || opt.state === 'steady' ? 'live_calibration' : 'watch'),
        reasonText: reportMode.reason || verdictDetail(perf),
    };
}

function refreshSourceBadges() {
    const snap = v13Snapshot();
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
}

function updateOverview() {
    const snap = v13Snapshot();
    const targetProfitGoal = Number((snap.capital.target ?? TARGET_EQUITY) - (snap.capital.start ?? START_EQUITY));
    const signedProgress = targetProfitGoal !== 0 ? (snap.modeRealizedPnl / targetProfitGoal) * 100 : 0;
    setTextIfExists('total-equity', money(snap.equity));
    setTextIfExists('usdt-avail', money(snap.available));
    setTextIfExists('version-pnl-label', 'V13 四模式已平倉合計');
    setMetricSource('total-equity', snap.equitySource);
    setMetricSource('usdt-avail', snap.equitySource);
    setMetricSource('total-profit', snap.activePnlSource);
    setMetricSource('capital-change', snap.modeRealizedSource);

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${snap.activePnl >= 0 ? '+' : ''}${money(snap.activePnl)}`;
        pnlEl.className = `value ${snap.activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = snap.activePnlSource;
    }

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${snap.modeRealizedPnl >= 0 ? '+' : ''}${money(snap.modeRealizedPnl)}`;
        capitalChangeEl.className = snap.modeRealizedPnl >= 0 ? 'gain' : 'loss';
        capitalChangeEl.title = snap.modeRealizedSource;
    }

    updateProgressCurve(snap.modeRealizedPnl, signedProgress);
    setTextIfExists('growth-title', 'V13 四模式已平倉盈虧曲線');

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
}

function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const snap = v13Snapshot();
    box.innerHTML = `
        <div class="health-summary">
            <div class="health-card"><span>目前狀態</span><strong class="${snap.activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(zhText(snap.verdict))}</strong><small>${escapeHtml(snap.snapshotAt)}</small></div>
            <div class="health-card"><span>OKX 活倉未實現盈虧</span><strong class="${snap.activePnl >= 0 ? 'gain' : 'loss'}">${signed(snap.activePnl)}</strong><small>${snap.activeCount} 持倉 / ${snap.potentialCount} 候選</small><small class="metric-source">${escapeHtml(snap.activePnlSource)}</small></div>
            <div class="health-card"><span>四模式已平倉合計</span><strong class="${snap.modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.modeRealizedPnl)}</strong><small>只看 V13 已驗證 closed trades</small><small class="metric-source">${escapeHtml(snap.modeRealizedSource)}</small></div>
            <div class="health-card"><span>資料可信度</span><strong class="good">同一快照</strong><small>/api/trades</small></div>
        </div>
    `;
}

function renderEngineHeartbeat() {
    const container = document.getElementById('engine-heartbeat');
    if (!container) return;
    container.innerHTML = v13Strategies().map((name) => {
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
}

function renderModeCards() {
    const container = document.getElementById('mode-cards');
    if (!container) return;
    container.innerHTML = '';
    v13Strategies().forEach((name) => {
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
                <div><span>期望值</span><strong class="${v13Num(perf.expectancy, 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                <div><span>PF</span><strong class="${v13Num(perf.profit_factor, 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
            </div>
            <p class="mode-note">${escapeHtml(model.reasonText || '')}</p>
            <p class="mode-note cumulative-note">已平倉合計：${escapeHtml(signed(realizedPnl, 1))}U <span class="metric-source-inline">來源：performance.total_pnl</span></p>
            <div class="rule-line">60U x 1.00 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr || '-'}x ATR / TP ${profile.tp_atr || '-'}x ATR</div>
        `;
        container.appendChild(card);
    });
}

function renderPerformance() {
    const tbody = document.getElementById('performance-body');
    if (!tbody) return;
    tbody.innerHTML = '';
    const metaEl = document.getElementById('performance-metadata');
    if (metaEl) {
        const snap = v13Snapshot();
        metaEl.textContent = `資料來源：/api/trades，同步時間：${snap.snapshotAt}。即時欄位看 OKX 活倉快照；學習欄位看 V13 已驗證 closed trades。`;
    }
    const names = v13Strategies().filter((name) => currentStrategyFilter === 'All' || name === currentStrategyFilter);
    if (!names.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty">${text.noData}</td></tr>`;
        return;
    }
    names.forEach((name) => {
        const model = buildStrategyCardModel(name);
        const perf = model.perf || {};
        const opt = model.opt || {};
        const livePnl = Number(model.livePnl || 0);
        const sample = v13Num(perf.sample ?? perf.total_trades, 0);
        const pf = v13Num(perf.profit_factor, 0);
        const exp = v13Num(perf.expectancy, 0);
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
}

// V13 canonical UI layer.
// Keep this block at the end of the file so it overrides older duplicate renderers.
function v13Num(value, fallback = 0) {
    const n = Number(value);
    return Number.isFinite(n) ? n : fallback;
}

function v13Strategies() {
    const ordered = Array.isArray(MODE_STRATEGIES) ? MODE_STRATEGIES : [];
    const known = new Set(ordered);
    const extras = Object.keys(profiles || {}).filter((name) => !known.has(name));
    return [...ordered, ...extras].filter((name) => name && name !== 'Manual' && name !== 'Recovered');
}

function v13ModeName(item) {
    try {
        return normalizedEngineBucket(item);
    } catch {
        return item?.strategy || item?.engine || item?.mode || 'Bot';
    }
}

function v13ActiveTrades() {
    return (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade && trade.status === 'active');
}

function v13PotentialTrades() {
    return (Array.isArray(currentTrades) ? currentTrades : []).filter((trade) => trade && trade.status === 'potential');
}

function v13TradesForMode(name, status) {
    const rows = status === 'active' ? v13ActiveTrades() : v13PotentialTrades();
    return rows.filter((trade) => v13ModeName(trade) === name);
}

function v13ModeRealizedPnl(name) {
    return v13Num(performanceData?.[name]?.total_pnl, 0);
}

function v13TotalModeRealizedPnl() {
    return v13Strategies().reduce((sum, name) => sum + v13ModeRealizedPnl(name), 0);
}

function v13Snapshot() {
    const capital = accountData?.capital || dashboardCapital || {};
    const report = reportData && typeof reportData === 'object' ? reportData : {};
    const activeTrades = v13ActiveTrades();
    const potentialTrades = v13PotentialTrades();
    const activePnl = activeTrades.reduce((sum, trade) => sum + v13Num(trade.pnl, 0), 0);
    const modeRealizedPnl = v13TotalModeRealizedPnl();
    const equity = v13Num(capital.equity ?? accountData?.usdtEq ?? accountData?.totalEq ?? 0, 0);
    const available = v13Num(accountData?.usdtAvail ?? capital.available ?? capital.usdtAvail ?? equity, 0);
    const snapshotAt = dashboardSnapshotAt || dashboardSourceState?.snapshotAt || report.server_time || '-';

    return {
        capital,
        report,
        activeTrades,
        potentialTrades,
        activeCount: activeTrades.length,
        potentialCount: potentialTrades.length,
        activePnl,
        modeRealizedPnl,
        equity,
        available,
        snapshotAt,
        verdict: report.verdict || (activeTrades.length ? 'running' : 'watch'),
        activePnlSource: '來源：/api/trades → OKX 活倉快照 → trade.pnl 合計',
        modeRealizedSource: '來源：/api/trades → performance[四模式].total_pnl 合計',
        equitySource: `來源：/api/trades → capital.equity (${capital.equity_basis || capital.source || 'OKX USDT 權益'})`,
    };
}

function getUnifiedReportMetrics() {
    const snap = v13Snapshot();
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
}

function buildStrategyCardModel(name) {
    const { liveModes, weakModes } = getUnifiedReportModes();
    const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
    const reportMode = reportModes.get(name) || {};
    const stats = strategyStats[name] || {};
    const perf = performanceData[name] || {};
    const opt = optimizerData[name] || {};
    const liveTrades = v13TradesForMode(name, 'active');
    const candidateTrades = v13TradesForMode(name, 'potential');
    const livePnl = liveTrades.reduce((sum, trade) => sum + v13Num(trade.pnl, 0), 0);
    const cumulativePnl = v13ModeRealizedPnl(name);
    const sample = v13Num(perf.sample ?? perf.total_trades, 0);
    const winRate = (perf.win_rate == null || sample === 0) ? '-' : pct(perf.win_rate, 1);
    const verdict = perf.verdict || stats.verdict || 'learning';
    const tierLabel = reportMode.tier ? modeTierLabel(reportMode.tier) : modeTierLabel(opt.state === 'exploit' || opt.state === 'steady' ? 'live_calibration' : 'watch');
    const reasonText = reportMode.reason || verdictDetail(perf);
    return {
        reportMode,
        stats,
        perf,
        opt,
        liveTrades,
        candidateTrades,
        livePnl,
        cumulativePnl,
        cumulativePnlSource: '來源：同一快照 performance.total_pnl',
        winRate,
        verdict,
        tierLabel,
        reasonText,
    };
}

function refreshSourceBadges() {
    const snap = v13Snapshot();
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
}

function updateOverview() {
    const snap = v13Snapshot();
    const activePnl = snap.activePnl;
    const realizedPnl = snap.modeRealizedPnl;
    const targetProfitGoal = Number((snap.capital.target ?? TARGET_EQUITY) - (snap.capital.start ?? START_EQUITY));
    const signedProgress = targetProfitGoal !== 0 ? (realizedPnl / targetProfitGoal) * 100 : 0;

    setTextIfExists('total-equity', money(snap.equity));
    setTextIfExists('usdt-avail', money(snap.available));

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = snap.activePnlSource;
    }

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${realizedPnl >= 0 ? '+' : ''}${money(realizedPnl)}`;
        capitalChangeEl.className = realizedPnl >= 0 ? 'gain' : 'loss';
        capitalChangeEl.title = snap.modeRealizedSource;
    }

    setTextIfExists('version-pnl-label', 'V13 四模式已平倉合計');
    setMetricSource('total-equity', snap.equitySource);
    setMetricSource('usdt-avail', snap.equitySource);
    setMetricSource('total-profit', snap.activePnlSource);
    setMetricSource('capital-change', snap.modeRealizedSource);

    updateProgressCurve(realizedPnl, signedProgress);
    setTextIfExists('growth-title', 'V13 四模式已平倉盈虧曲線');

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(snap.verdict);

    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${snap.activeCount}</span><strong>即時持倉</strong></div>
            <div><span>${snap.potentialCount}</span><strong>候選訊號</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮盈</strong></div>
        `;
    }
}

function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const snap = v13Snapshot();
    box.innerHTML = `
        <div class="health-summary">
            <div class="health-card">
                <span>目前狀態</span>
                <strong class="${snap.activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(zhText(snap.verdict))}</strong>
                <small>${escapeHtml(snap.snapshotAt)}</small>
            </div>
            <div class="health-card">
                <span>OKX 活倉未實現盈虧</span>
                <strong class="${snap.activePnl >= 0 ? 'gain' : 'loss'}">${signed(snap.activePnl)}</strong>
                <small>${snap.activeCount} 持倉 / ${snap.potentialCount} 候選</small>
                <small class="metric-source">${escapeHtml(snap.activePnlSource)}</small>
            </div>
            <div class="health-card">
                <span>四模式已平倉合計</span>
                <strong class="${snap.modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(snap.modeRealizedPnl)}</strong>
                <small>只看 V13 訓練/已驗證 closed trades</small>
                <small class="metric-source">${escapeHtml(snap.modeRealizedSource)}</small>
            </div>
            <div class="health-card">
                <span>資料可信度</span>
                <strong class="good">同一快照</strong>
                <small>/api/trades</small>
            </div>
        </div>
    `;
}

function renderEngineHeartbeat() {
    const container = document.getElementById('engine-heartbeat');
    if (!container) return;
    container.innerHTML = v13Strategies().map((name) => {
        const model = buildStrategyCardModel(name);
        const perf = model.perf || {};
        const opt = model.opt || {};
        const livePnl = Number(model.livePnl || 0);
        const realizedPnl = Number(model.cumulativePnl || 0);
        const conf = opt.capital_mult != null ? Number(opt.capital_mult).toFixed(2) : (perf.confidence != null ? Number(perf.confidence).toFixed(2) : '1.00');
        const state = verdictLabel(model.verdict || 'learning');
        return `
            <div class="eng-card">
                <div class="eng-head">
                    <strong>${escapeHtml(strategyLabel(name))}</strong>
                    <span class="eng-verdict">${escapeHtml(state)}</span>
                </div>
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
}

function renderModeCards() {
    const container = document.getElementById('mode-cards');
    if (!container) return;
    container.innerHTML = '';
    v13Strategies().forEach((name) => {
        const profile = profiles[name] || {};
        const model = buildStrategyCardModel(name);
        const livePnl = Number(model.livePnl || 0);
        const realizedPnl = Number(model.cumulativePnl || 0);
        const perf = model.perf || {};
        const card = document.createElement('article');
        card.className = 'mode-card';
        card.innerHTML = `
            <div class="mode-card-head">
                <strong>${escapeHtml(strategyLabel(name))}</strong>
                ${verdictBadge(model.verdict)}
            </div>
            <p>${escapeHtml(model.tierLabel || '觀察中')}</p>
            <div class="mode-stats">
                <div><span>即時持倉</span><strong class="${model.liveTrades.length > 0 ? 'gain' : ''}">${model.liveTrades.length}</strong></div>
                <div><span>候選</span><strong>${model.candidateTrades.length}</strong></div>
                <div><span>活倉浮盈</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}</strong><small class="metric-source">OKX 活倉快照</small></div>
                <div><span>勝率</span><strong>${escapeHtml(model.winRate)}</strong></div>
                <div><span>期望值</span><strong class="${v13Num(perf.expectancy, 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                <div><span>PF</span><strong class="${v13Num(perf.profit_factor, 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
            </div>
            <p class="mode-note">${escapeHtml(model.reasonText || '')}</p>
            <p class="mode-note cumulative-note">已平倉合計：${escapeHtml(signed(realizedPnl, 1))}U <span class="metric-source-inline">來源：performance.total_pnl</span></p>
            <div class="rule-line">60U x 1.00 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr || '-'}x ATR / TP ${profile.tp_atr || '-'}x ATR</div>
        `;
        container.appendChild(card);
    });
}

function renderPerformance() {
    const tbody = document.getElementById('performance-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    const metaEl = document.getElementById('performance-metadata');
    if (metaEl) {
        const snap = v13Snapshot();
        metaEl.textContent = `資料來源：/api/trades，同步時間：${snap.snapshotAt}。即時欄位看 OKX 活倉快照；學習欄位看 V13 已驗證 closed trades。`;
        metaEl.title = '此表不再使用舊帳戶層累積值。';
    }

    const names = v13Strategies().filter((name) => currentStrategyFilter === 'All' || name === currentStrategyFilter);
    if (!names.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="empty">${text.noData}</td></tr>`;
        return;
    }

    names.forEach((name) => {
        const model = buildStrategyCardModel(name);
        const perf = model.perf || {};
        const opt = model.opt || {};
        const livePnl = Number(model.livePnl || 0);
        const pf = v13Num(perf.profit_factor, 0);
        const exp = v13Num(perf.expectancy, 0);
        const sample = v13Num(perf.sample ?? perf.total_trades, 0);
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <strong>${escapeHtml(strategyLabel(name))}</strong>
                <small>來源：同一份 /api/trades 快照</small>
            </td>
            <td>
                ${model.liveTrades.length} / ${model.candidateTrades.length}
                <small>${escapeHtml(verdictLabel(model.verdict || 'learning'))}</small>
            </td>
            <td class="${livePnl >= 0 ? 'gain' : 'loss'}">
                ${money(livePnl)}
                <small>OKX 活倉快照</small>
            </td>
            <td>
                ${sample} / ${perf.win_rate == null || sample === 0 ? '-' : pct(perf.win_rate, 1)}
                <small>已驗證 closed trades / 勝率</small>
            </td>
            <td class="${pf >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</td>
            <td>
                <span class="gain">${money(perf.avg_win)}</span> / <span class="loss">${money(perf.avg_loss)}</span>
            </td>
            <td class="${exp >= 0 ? 'gain' : 'loss'}">${money(exp)}</td>
            <td>
                ${verdictBadge(perf.verdict || model.verdict)}
                <div style="font-size: 10px; color: #a1a1aa; margin-top: 4px; line-height: 1.3;">
                    optimizer：${escapeHtml(optimizerLabel(opt))}<br>
                    已平倉合計：${escapeHtml(signed(model.cumulativePnl, 1))}U
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function getUnifiedReportMetrics() {
    const capital = accountData.capital || {};
    const activeTrades = currentTrades.filter((trade) => trade.status === 'active');
    const potentialTrades = currentTrades.filter((trade) => trade.status === 'potential');
    const report = reportData && typeof reportData === 'object' ? reportData : {};
    const capitalUnrealized = Number(
        capital.strategy_unrealized ??
        report.active_pnl ??
        activeTrades.reduce((sum, trade) => sum + Number(trade.pnl || 0), 0)
    );
    const capitalSnapshotAvailable = Boolean(capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    return {
        activeCount: Number(report.active_count ?? activeTrades.length ?? 0),
        potentialCount: Number(report.potential_count ?? potentialTrades.length ?? 0),
        activePnl: capitalUnrealized,
        sessionActiveCount: Number(report.session_active_count ?? 0),
        sessionPotentialCount: Number(report.session_potential_count ?? 0),
        sessionActivePnl: Number(report.session_active_pnl ?? 0),
        sessionRealizedPnl: Number(report.session_realized_pnl ?? 0),
        activePnlSource: capital.strategy_unrealized_source || report.active_pnl_source || 'OKX / 活倉快照',
        sessionActiveSource: report.session_active_pnl_source || 'OKX / 活倉快照',
        sessionRealizedSource: report.session_realized_pnl_source || '已驗證歷史 / session alphaPnl',
        verdict: report.verdict || '觀察中',
        protectionRule: report.protection_rule || '-',
        serverTime: report.server_time || '-',
        positions: Array.isArray(report.positions) ? report.positions : [],
        trackedPositions: Array.isArray(report.tracked_positions) ? report.tracked_positions : [],
        capital,
        capitalSnapshotAvailable,
        capitalSource: capital.account_layer_source || capital.cumulative_source || capital.pnl_source || (capitalSnapshotAvailable ? 'OKX / 帳戶快照' : '帳戶快照不可用 / Session 推算'),
    };
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalSnapshotAvailable = Boolean(metrics.capitalSnapshotAvailable ?? capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    const capitalPnl = capitalSnapshotAvailable ? Number(capital.account_layer_pnl ?? capital.cumulative_pnl ?? 0) : null;
    const sessionPnl = Number(capital.session_cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.account_layer_source || capital.cumulative_source || 'OKX / 帳戶快照';

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        if (capitalPnl == null || !Number.isFinite(capitalPnl)) {
            capitalChangeEl.textContent = '--';
            capitalChangeEl.className = 'value';
            capitalChangeEl.title = 'OKX 帳戶快照不可用，未以策略推算值冒充帳戶層';
        } else {
            capitalChangeEl.textContent = `${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)}`;
            capitalChangeEl.className = capitalPnl >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = `帳戶層來源：${capitalSource}`;
        }
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧（帳戶層）' : 'V13 累積盈虧（帳戶快照不可用）';
    setMetricSource('capital-change', capitalSnapshotAvailable ? `來源：${capitalSource}` : '來源：OKX 帳戶快照不可用 / 只顯示 Session 推算');

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (sessionPnl / targetProfitGoal) * 100 : 0);
    const curvePnl = capitalSnapshotAvailable ? Number(capitalPnl ?? 0) : sessionPnl;
    updateProgressCurve(curvePnl, signedProgress);

    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧曲線（帳戶層）' : 'V13 Session 推算曲線（非帳戶層）';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }
}

function renderHistory() {
    const tbody = document.getElementById('history-body');
    const summary = document.getElementById('history-summary');
    tbody.innerHTML = '';
    const rows = filtered(historyData).slice(0, 80);
    const closedTradeTotalPnl = rows.reduce((sum, item) => {
        const info = item.info || {};
        return sum + Number(item.realizedPnl || info.realizedPnl || 0);
    }, 0);
    if (summary) {
        summary.innerHTML = `
            <div class="summary-card">
                <span>已平倉筆數</span>
                <strong>${rows.length}</strong>
            </div>
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${closedTradeTotalPnl >= 0 ? 'gain' : 'loss'}">${signed(closedTradeTotalPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>本頁口徑</span>
                <strong>只看 closed trades</strong>
            </div>
        `;
    }
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
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl, 4)}<small>手續費 ${signed(fee, 4)} / 資金費 ${signed(funding, 4)}</small></td>
            <td>${item.timestamp ? new Date(item.timestamp).toLocaleString() : '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

function renderModeCards() {
    const container = document.getElementById('mode-cards');
    if (!container) return;
    container.innerHTML = '';
    const { liveModes, weakModes } = getUnifiedReportModes();
    Object.entries(profiles).forEach(([name, profile]) => {
        const model = buildStrategyCardModel(name);
        const perf = model.perf;
        const opt = model.opt;
        const liveTrades = model.liveTrades;
        const candidateTrades = model.candidateTrades;
        const livePnl = model.livePnl;
        const pnl = model.cumulativePnl;
        const pnlSource = model.cumulativePnlSource || '來源：已驗證歷史 / alphaPnl';
        const winRate = model.winRate;
        const verdict = model.verdict;
        const tierLabel = model.tierLabel;
        const reasonText = model.reasonText;
        const card = document.createElement('article');
        card.className = 'mode-card';
        card.innerHTML = `
            <div class="mode-card-head">
                <strong>${strategyLabel(name)}</strong>
                ${verdictBadge(verdict)}
            </div>
            <p>${tierLabel}</p>
            <div class="mode-stats">
                <div><span>持倉</span><strong class="${liveTrades.length > 0 ? 'gain' : ''}">${liveTrades.length}</strong></div>
                <div><span>候選</span><strong>${candidateTrades.length}</strong></div>
                <div><span>活倉浮動</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}</strong><small class="metric-source">來源：OKX / 活倉快照</small></div>
                <div><span>勝率</span><strong>${winRate}</strong></div>
                <div><span>期望值</span><strong class="${Number(perf.expectancy || 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                <div><span>PF</span><strong class="${Number(perf.profit_factor || 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
            </div>
            <p class="mode-note">${escapeHtml(reasonText)}</p>
            <p class="mode-note cumulative-note">模式已實現盈虧 ${escapeHtml(signed(pnl, 1))}U<span class="metric-source-inline">${escapeHtml(pnlSource)}</span></p>
            <div class="rule-line">60U x 1.00 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr}x ATR / TP ${profile.tp_atr}x ATR</div>
        `;
        container.appendChild(card);
    });
}

function renderEngineHeartbeat() {
    const container = document.getElementById('engine-heartbeat');
    if (!container) return;
    const engines = ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'];
    container.innerHTML = engines.map((name) => {
        const meta = ENGINE_META[name] || { icon: '•', desc: name, color: '#888' };
        const model = buildStrategyCardModel(name);
        const stats = model.stats;
        const perf = model.perf;
        const opt = model.opt;
        const active = model.liveTrades.length;
        const signals = model.candidateTrades.length;
        const livePnl = Number(model.livePnl || 0);
        const cumulativePnl = Number(model.cumulativePnl || 0);
        const cumulativePnlSource = model.cumulativePnlSource || '來源：已驗證歷史 / alphaPnl';
        const wr = model.winRate;
        const conf = opt.capital_mult != null ? opt.capital_mult.toFixed(2) : (stats.confidence != null ? stats.confidence.toFixed(2) : '1.00');
        const verdict = verdictLabel(model.verdict);
        const verdictColor = perf.state === 'exploit' ? '#22c55e' : perf.state === 'steady' ? '#60a5fa' : perf.state === 'pause' ? '#ef4444' : '#f59e0b';
        return `
        <div class="eng-card" style="border-top: 3px solid ${meta.color}">
            <div class="eng-head">
                <strong>${escapeHtml(meta.icon)} ${escapeHtml(strategyLabel(name))}</strong>
                <span class="eng-verdict" style="color:${verdictColor}">${escapeHtml(verdict)}</span>
            </div>
            <div class="eng-desc">${escapeHtml(meta.desc)}</div>
            <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                <div><span>勝率</span><strong>${escapeHtml(wr)}</strong></div>
                <div><span>信心</span><strong>${escapeHtml(conf)}x</strong></div>
                <div><span>持倉</span><strong>${escapeHtml(active)} 筆</strong></div>
                <div><span>活倉浮動</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(livePnl, 1))}U</strong><small class="metric-source">來源：OKX / 活倉快照</small></div>
                <div><span>模式已實現</span><strong class="${cumulativePnl >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(cumulativePnl, 1))}U</strong><small class="metric-source">${escapeHtml(cumulativePnlSource)}</small></div>
            </div>
            <div class="eng-scan-status">${signals > 0 ? `<span class="eng-scanning">掃描中 ${signals} 個候選</span>` : `<span class="eng-idle">待命</span>`}</div>
        </div>`;
    }).join('');
}

function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const { liveModes, weakModes } = getUnifiedReportModes();
    const metrics = getUnifiedReportMetrics();
    const activeCount = Number(metrics.activeCount || 0);
    const potentialCount = Number(metrics.potentialCount || 0);
    const activePnl = Number(metrics.activePnl || 0);
    const sessionActivePnl = Number(metrics.sessionActivePnl || 0);
    const sessionRealizedPnl = Number(metrics.sessionRealizedPnl || 0);
    const activePnlSource = metrics.activePnlSource || 'OKX / 活倉快照';
    const sessionRealizedSource = metrics.sessionRealizedSource || '已驗證歷史 / session alphaPnl';
    const verdict = zhText(metrics.verdict || '-');
    const serverTime = metrics.serverTime || '-';
    box.innerHTML = `
        <div class="health-summary">
            <div class="health-card">
                <span>狀態</span>
                <strong class="${activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(verdict)}</strong>
                <small>${escapeHtml(serverTime)}</small>
            </div>
            <div class="health-card">
                <span>活倉浮動盈虧</span>
                <strong class="${activePnl >= 0 ? 'gain' : 'loss'}">${signed(activePnl)}</strong>
                <small>${activeCount} 持倉 / ${potentialCount} 候選</small>
                <small class="metric-source">來源：${escapeHtml(activePnlSource)}</small>
            </div>
            <div class="health-card">
                <span>Session 已實現</span>
                <strong class="${sessionRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(sessionRealizedPnl)}</strong>
                <small>Session 浮動 ${signed(sessionActivePnl)}</small>
                <small class="metric-source">來源：${escapeHtml(sessionRealizedSource)}</small>
            </div>
            <div class="health-card">
                <span>模式數</span>
                <strong class="${liveModes.length > 0 ? 'gain' : 'loss'}">${liveModes.length} / ${weakModes.length}</strong>
                <small>活躍 / 觀察</small>
            </div>
        </div>
    `;
}

function getUnifiedReportMetrics() {
    const capital = accountData.capital || {};
    const activeTrades = currentTrades.filter((trade) => trade.status === 'active');
    const potentialTrades = currentTrades.filter((trade) => trade.status === 'potential');
    const report = reportData && typeof reportData === 'object' ? reportData : {};
    const capitalUnrealized = Number(
        capital.strategy_unrealized ??
        report.active_pnl ??
        activeTrades.reduce((sum, trade) => sum + Number(trade.pnl || 0), 0)
    );
    const capitalSnapshotAvailable = Boolean(capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    return {
        activeCount: Number(report.active_count ?? activeTrades.length ?? 0),
        potentialCount: Number(report.potential_count ?? potentialTrades.length ?? 0),
        activePnl: capitalUnrealized,
        sessionActiveCount: Number(report.session_active_count ?? 0),
        sessionPotentialCount: Number(report.session_potential_count ?? 0),
        sessionActivePnl: Number(report.session_active_pnl ?? 0),
        sessionRealizedPnl: Number(report.session_realized_pnl ?? 0),
        activePnlSource: capital.strategy_unrealized_source || report.active_pnl_source || 'OKX / 活倉快照',
        sessionActiveSource: report.session_active_pnl_source || 'OKX / 活倉快照',
        sessionRealizedSource: report.session_realized_pnl_source || '已驗證歷史 / session alphaPnl',
        verdict: report.verdict || '觀察中',
        protectionRule: report.protection_rule || '-',
        serverTime: report.server_time || '-',
        positions: Array.isArray(report.positions) ? report.positions : [],
        trackedPositions: Array.isArray(report.tracked_positions) ? report.tracked_positions : [],
        capital,
        capitalSnapshotAvailable,
        capitalSource: capital.account_layer_source || capital.cumulative_source || capital.pnl_source || (capitalSnapshotAvailable ? 'OKX / 帳戶快照' : '帳戶快照不可用 / Session 推算'),
    };
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalSnapshotAvailable = Boolean(metrics.capitalSnapshotAvailable);
    const capitalDisplayPnl = capitalSnapshotAvailable
        ? Number(capital.account_layer_pnl ?? capital.cumulative_pnl ?? 0)
        : null;
    const sessionDisplayPnl = Number(capital.session_cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.account_layer_source || capital.cumulative_source || 'OKX / 帳戶快照';

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }

    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        if (capitalDisplayPnl == null || !Number.isFinite(capitalDisplayPnl)) {
            capitalChangeEl.textContent = '--';
            capitalChangeEl.className = 'value';
            capitalChangeEl.title = 'OKX 帳戶快照不可用，未以策略推算值冒充帳戶層';
        } else {
            capitalChangeEl.textContent = `${capitalDisplayPnl >= 0 ? '+' : ''}${money(capitalDisplayPnl)}`;
            capitalChangeEl.className = capitalDisplayPnl >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = `帳戶層來源：${capitalSource}`;
        }
    }

    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) {
        capitalLabel.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧（帳戶層）' : 'V13 累積盈虧（帳戶快照不可用）';
    }
    setMetricSource('capital-change', capitalSnapshotAvailable ? `來源：${capitalSource}` : '來源：OKX 帳戶快照不可用 / 只顯示 Session 推算');

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (sessionDisplayPnl / targetProfitGoal) * 100 : 0);
    const curvePnl = capitalSnapshotAvailable ? capitalDisplayPnl : sessionDisplayPnl;
    updateProgressCurve(curvePnl, signedProgress);

    const curveLabel = document.getElementById('curve-label');
    if (curveLabel) {
        const verTag = (currentStrategyVersion.match(/v\d+/i)?.[0] || 'V13').toUpperCase();
        curveLabel.textContent = capitalSnapshotAvailable
            ? `${verTag} 累積盈虧 ${curvePnl >= 0 ? '+' : ''}${money(curvePnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`
            : `${verTag} Session 推算 ${curvePnl >= 0 ? '+' : ''}${money(curvePnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`;
    }

    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) {
        growthTitle.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧曲線（帳戶層）' : 'V13 Session 推算曲線（非帳戶層）';
    }

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }
}

function renderHistory() {
    const tbody = document.getElementById('history-body');
    const summary = document.getElementById('history-summary');
    tbody.innerHTML = '';
    const rows = filtered(historyData).slice(0, 80);
    const closedTradeTotalPnl = rows.reduce((sum, item) => {
        const info = item.info || {};
        return sum + Number(item.realizedPnl || info.realizedPnl || 0);
    }, 0);

    if (summary) {
        summary.innerHTML = `
            <div class="summary-card">
                <span>已平倉筆數</span>
                <strong>${rows.length}</strong>
            </div>
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${closedTradeTotalPnl >= 0 ? 'gain' : 'loss'}">${signed(closedTradeTotalPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>本頁口徑</span>
                <strong>只看 closed trades</strong>
            </div>
        `;
    }

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
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl, 4)}<small>手續費 ${signed(fee, 4)} / 資金費 ${signed(funding, 4)}</small></td>
            <td>${item.timestamp ? new Date(item.timestamp).toLocaleString() : '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalSnapshotAvailable = Boolean(metrics.capitalSnapshotAvailable ?? capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    const capitalPnl = capitalSnapshotAvailable ? Number(capital.account_layer_pnl ?? capital.cumulative_pnl ?? 0) : null;
    const sessionPnl = Number(capital.session_cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.account_layer_source || capital.cumulative_source || 'OKX / 帳戶快照';

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }

    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)}`;
        capitalChangeEl.className = capitalPnl >= 0 ? 'gain' : 'loss';
        capitalChangeEl.title = `帳戶淨值變化來源：${capitalSource}`;
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = 'V13 帳戶淨值變化';
    setMetricSource('capital-change', `來源：${capitalSource}`);

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (capitalPnl / targetProfitGoal) * 100 : 0);
    updateProgressCurve(capitalPnl, signedProgress);
    const curveLabel = document.getElementById('curve-label');
    if (curveLabel) {
        curveLabel.textContent = `V13 帳戶淨值變化 ${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`;
    }
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = 'V13 帳戶淨值變化曲線';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }
}

function renderHistory() {
    const tbody = document.getElementById('history-body');
    const summary = document.getElementById('history-summary');
    tbody.innerHTML = '';
    const rows = filtered(historyData).slice(0, 80);
    const closedTradeCount = rows.length;
    const closedTradeTotalPnl = rows.reduce((sum, item) => {
        const info = item.info || {};
        return sum + Number(item.realizedPnl || info.realizedPnl || 0);
    }, 0);

    if (summary) {
        summary.innerHTML = `
            <div class="summary-card">
                <span>已平倉筆數</span>
                <strong>${closedTradeCount}</strong>
            </div>
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${closedTradeTotalPnl >= 0 ? 'gain' : 'loss'}">${signed(closedTradeTotalPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>本頁口徑</span>
                <strong>只看 closed trades</strong>
            </div>
        `;
    }

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
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl, 4)}<small>手續費 ${signed(fee, 4)} / 資金費 ${signed(funding, 4)}</small></td>
            <td>${item.timestamp ? new Date(item.timestamp).toLocaleString() : '-'}</td>
        `;
        tbody.appendChild(row);
    });
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalSnapshotAvailable = Boolean(metrics.capitalSnapshotAvailable ?? capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    const capitalPnl = capitalSnapshotAvailable ? Number(capital.account_layer_pnl ?? capital.cumulative_pnl ?? 0) : null;
    const sessionPnl = Number(capital.session_cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.cumulative_source || 'OKX / 帳戶快照';
    const modeRealizedPnl = Object.values(performanceData || {}).reduce((sum, perf) => sum + Number(perf?.total_pnl || 0), 0);
    const historyRealizedPnl = (Array.isArray(historyData) ? historyData : []).reduce((sum, item) => {
        const info = item?.info || {};
        return sum + Number(item?.realizedPnl || info?.realizedPnl || 0);
    }, 0);

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChange = capitalPnl;
    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        if (capitalChange == null || !Number.isFinite(capitalChange)) {
            capitalChangeEl.textContent = '--';
            capitalChangeEl.className = 'value';
            capitalChangeEl.title = 'OKX 帳戶快照不可用，未以策略推算值冒充帳戶層';
        } else {
            capitalChangeEl.textContent = `${capitalChange >= 0 ? '+' : ''}${money(capitalChange)}`;
            capitalChangeEl.className = capitalChange >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = `帳戶層來源：${capitalSource}`;
        }
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧（帳戶層）' : 'V13 累積盈虧（帳戶快照不可用）';
    setMetricSource('capital-change', capitalSnapshotAvailable ? `來源：${capitalSource}` : '來源：OKX 帳戶快照不可用 / 只顯示 Session 推算');

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (sessionPnl / targetProfitGoal) * 100 : 0);
    const curvePnl = capitalSnapshotAvailable ? Number(capitalPnl ?? 0) : sessionPnl;
    updateProgressCurve(curvePnl, signedProgress);
    const curveLabel = document.getElementById('curve-label');
    if (curveLabel) {
        curveLabel.textContent = `V13 帳戶淨值變化 ${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`;
    }
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧曲線（帳戶層）' : 'V13 Session 推算曲線（非帳戶層）';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }

    const historySummary = document.getElementById('history-summary');
    if (historySummary) {
        historySummary.innerHTML = `
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${historyRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(historyRealizedPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>模式合計已實現盈虧</span>
                <strong class="${modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(modeRealizedPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>帳戶淨值變化</span>
                <strong class="${capitalPnl >= 0 ? 'gain' : 'loss'}">${signed(capitalPnl, 4)}</strong>
            </div>
        `;
    }
}

function buildStrategyCardModel(name) {
    const { liveModes, weakModes } = getUnifiedReportModes();
    const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
    const reportMode = reportModes.get(name) || {};
    const stats = strategyStats[name] || {};
    const perf = performanceData[name] || {};
    const opt = optimizerData[name] || {};
    const liveTrades = currentTrades.filter((trade) => trade.status === 'active' && normalizedEngineBucket(trade) === name);
    const candidateTrades = currentTrades.filter((trade) => trade.status === 'potential' && normalizedEngineBucket(trade) === name);
    const livePnl = liveTrades.reduce((sum, trade) => sum + Number(trade.pnl || 0), 0);
    const cumulativePnl = Number(stats.pnl || perf.total_pnl || 0);
    const cumulativePnlSource = perf.pnl_source_label || '來源：已驗證歷史 / alphaPnl';
    const winRate = (perf.win_rate == null || perf.total_trades === 0) ? '-' : pct(perf.win_rate, 1);
    const verdict = perf.verdict || stats.verdict || 'learning';
    const tierLabel = reportMode.tier ? modeTierLabel(reportMode.tier) : modeTierLabel(opt.state === 'exploit' || opt.state === 'steady' ? 'live_calibration' : 'watch');
    const reasonText = reportMode.reason || verdictDetail(perf);
    return {
        reportMode,
        stats,
        perf,
        opt,
        liveTrades,
        candidateTrades,
        livePnl,
        cumulativePnl,
        cumulativePnlSource,
        winRate,
        verdict,
        tierLabel,
        reasonText,
    };
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalPnl = Number(capital.cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.cumulative_source || 'OKX / 帳戶快照';
    const modeRealizedPnl = Object.values(performanceData || {}).reduce((sum, perf) => sum + Number(perf?.total_pnl || 0), 0);
    const historyRealizedPnl = (Array.isArray(historyData) ? historyData : []).reduce((sum, item) => {
        const info = item?.info || {};
        return sum + Number(item?.realizedPnl || info?.realizedPnl || 0);
    }, 0);

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChange = capitalPnl;
    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${capitalChange >= 0 ? '+' : ''}${money(capitalChange)}`;
        capitalChangeEl.className = capitalChange >= 0 ? 'gain' : 'loss';
        capitalChangeEl.title = `帳戶淨值變化來源：${capitalSource}`;
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = 'V13 帳戶淨值變化';
    setMetricSource('capital-change', `來源：${capitalSource}`);

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (capitalPnl / targetProfitGoal) * 100 : 0);
    updateProgressCurve(capitalPnl, signedProgress);
    const curveLabel = document.getElementById('curve-label');
    if (curveLabel) {
        curveLabel.textContent = `V13 帳戶淨值變化 ${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`;
    }
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = 'V13 帳戶淨值變化曲線';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }

    const historySummary = document.getElementById('history-summary');
    if (historySummary) {
        historySummary.innerHTML = `
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${historyRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(historyRealizedPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>模式合計已實現盈虧</span>
                <strong class="${modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(modeRealizedPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>帳戶淨值變化</span>
                <strong class="${capitalPnl >= 0 ? 'gain' : 'loss'}">${signed(capitalPnl, 4)}</strong>
            </div>
        `;
    }
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalPnl = Number(capital.cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.cumulative_source || 'OKX / 帳戶快照';
    const modeRealizedPnl = Object.values(performanceData || {}).reduce((sum, perf) => sum + Number(perf?.total_pnl || 0), 0);
    const historyRealizedPnl = (Array.isArray(historyData) ? historyData : []).reduce((sum, item) => {
        const info = item?.info || {};
        return sum + Number(item?.realizedPnl || info?.realizedPnl || 0);
    }, 0);

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChange = capitalPnl;
    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${capitalChange >= 0 ? '+' : ''}${money(capitalChange)}`;
        capitalChangeEl.className = capitalChange >= 0 ? 'gain' : 'loss';
        capitalChangeEl.title = `帳戶淨值變化來源：${capitalSource}`;
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = 'V13 帳戶淨值變化';
    setMetricSource('capital-change', `來源：${capitalSource}`);

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (capitalPnl / targetProfitGoal) * 100 : 0);
    updateProgressCurve(capitalPnl, signedProgress);
    const curveLabel = document.getElementById('curve-label');
    if (curveLabel) {
        curveLabel.textContent = `V13 帳戶淨值變化 ${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`;
    }
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = 'V13 帳戶淨值變化曲線';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }

    const historySummary = document.getElementById('history-summary');
    if (historySummary) {
        historySummary.innerHTML = `
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${historyRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(historyRealizedPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>模式合計已實現盈虧</span>
                <strong class="${modeRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(modeRealizedPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>帳戶淨值變化</span>
                <strong class="${capitalPnl >= 0 ? 'gain' : 'loss'}">${signed(capitalPnl, 4)}</strong>
            </div>
        `;
    }
}

function renderModeCards() {
    const container = document.getElementById('mode-cards');
    container.innerHTML = '';
    const { liveModes, weakModes } = getUnifiedReportModes();
    const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
    Object.entries(profiles).forEach(([name, profile]) => {
        const model = buildStrategyCardModel(name);
        const reportMode = reportModes.get(name) || {};
        const stats = model.stats;
        const perf = model.perf;
        const opt = model.opt;
        const liveTrades = model.liveTrades;
        const candidateTrades = model.candidateTrades;
        const livePnl = model.livePnl;
        const pnl = model.cumulativePnl;
        const winRate = model.winRate;
        const verdict = model.verdict;
        const tierLabel = model.tierLabel;
        const reasonText = model.reasonText;
        const card = document.createElement('article');
        card.className = 'mode-card';
        card.innerHTML = `
            <div class="mode-card-head">
                <strong>${strategyLabel(name)}</strong>
                ${verdictBadge(verdict)}
            </div>
            <p>${tierLabel}</p>
            <div class="mode-stats">
                <div><span>即時持倉</span><strong class="${liveTrades.length > 0 ? 'gain' : ''}">${liveTrades.length}</strong></div>
                <div><span>候選</span><strong>${candidateTrades.length}</strong></div>
                <div><span>即時浮動</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}</strong></div>
                <div><span>訓練勝率</span><strong>${winRate}</strong></div>
                <div><span>訓練期望</span><strong class="${Number(perf.expectancy || 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                <div><span>訓練PF</span><strong class="${Number(perf.profit_factor || 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
            </div>
            <p class="mode-note">${escapeHtml(reasonText)}</p>
            <p class="mode-note optimizer-note">訓練調參：${optimizerLine(opt)}</p>
            <p class="mode-note cumulative-note">訓練累積盈虧 ${escapeHtml(signed(pnl, 1))}U</p>
            <div class="rule-line">60U x \u4fe1\u5fc3 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr}x ATR / TP ${profile.tp_atr}x ATR</div>
        `;
        container.appendChild(card);
    });
}

function verdictBadge(verdict) {
    const klass = verdict === 'scale_up' || verdict === 'keep' ? 'good' : verdict === 'pause' ? 'bad' : 'warn';
    return `<span class="decision ${klass}">${verdictLabel(verdict || 'learning')}</span>`;
}

function deprecatedRenderPerformance() {
    const tbody = document.getElementById('performance-body');
    tbody.innerHTML = '';
    Object.keys(profiles || {}).forEach((name) => {
        if (currentStrategyFilter !== 'All' && name !== currentStrategyFilter) return;
        const model = buildStrategyCardModel(name);
        const perf = model.perf;
        const opt = model.opt;
        const pf = Number(perf.profit_factor || 0);
        const exp = Number(perf.expectancy || 0);
        const stateLabel = optimizerLabel(opt);
        const tunedAtr = perf.tuned_sl_atr ? `ATR 止損系數: ${perf.tuned_sl_atr}` : '';
        const confidenceText = perf.confidence ? `AI 信心權重: ${perf.confidence}x` : '';
        const row = document.createElement('tr');
        row.innerHTML = `
            <td><strong>${strategyLabel(name)}</strong><small>AI 權重: ${perf.weight ?? '1.0'}x / 健康度 ${perf.health_score ?? '-'}</small></td>
            <td>${perf.sample || 0} / ${perf.win_rate == null ? '-' : pct(perf.win_rate, 1)}</td>
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

function deprecatedRenderTrades() {
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
        const protectionVerified = trade.exchange_protection_verified === true || String(trade.exchange_protection_verified || '').toLowerCase() === 'true';
        const protectionFailed = trade.protection_status === 'failed' || trade.trailing_stage === 'protection_failed' || (isActive && trade.protection_status === 'confirmed' && !protectionVerified);
        const protectionText = protectionFailed
            ? (trade.protection_status === 'confirmed' && !protectionVerified ? 'OKX \u4fdd\u8b77\u55ae\u672a\u9a57\u8b49' : '\u4fdd\u8b77\u55ae\u5931\u6557')
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

function renderEntryEfficiency() {
    const summary = document.getElementById('entry-efficiency-summary');
    const reasons = document.getElementById('entry-block-reasons');
    if (!summary || !reasons) return;
    const data = entryEfficiencyData && typeof entryEfficiencyData === 'object' ? entryEfficiencyData : {};
    const scan = data.scan_policy || {};
    const edge = data.edge_policy || {};
    const radarCounts = data.radar_counts || {};
    const scanned = Object.values(radarCounts).reduce((sum, value) => sum + Number(value || 0), 0);
    const modeLabel = data.arbitrage_enabled
        ? '\u5957\u5229\u5f15\u64ce'
        : '\u65b9\u5411\u7b56\u7565\uff08\u975e\u771f\u6b63\u5957\u5229\uff09';

    summary.innerHTML = `
        <div class="summary-card">
            <span>\u76ee\u524d\u6a21\u5f0f</span>
            <strong>${modeLabel}</strong>
        </div>
        <div class="summary-card">
            <span>\u5019\u9078 / \u6301\u5009</span>
            <strong>${Number(data.potential_count || 0)} / ${Number(data.active_count || 0)}</strong>
        </div>
        <div class="summary-card">
            <span>\u6383\u63cf\u901f\u5ea6</span>
            <strong>${Number(scan.symbols_per_loop || 0)}\u6a94 / ${Number(scan.loop_seconds || 0)}\u79d2</strong>
        </div>
        <div class="summary-card">
            <span>\u96f7\u9054\u5373\u6642\u6a23\u672c</span>
            <strong>${scanned}</strong>
        </div>
        <div class="summary-card">
            <span>\u6700\u4f4e\u9810\u671f\u6de8\u5229</span>
            <strong>${money(edge.min_expected_net_profit_usdt || 0)}</strong>
        </div>
        <div class="summary-card">
            <span>\u6bdb\u5229 / \u6210\u672c\u9580\u6abb</span>
            <strong>${Number(edge.min_gross_to_cost_ratio || 0).toFixed(2)}x</strong>
        </div>
    `;

    const topReasons = Array.isArray(data.top_block_reasons) ? data.top_block_reasons : [];
    reasons.innerHTML = topReasons.length
        ? topReasons.map((item) => `<span>${Number(item.count || 0)}x ${zhReason(item.reason || '-')}</span>`).join('')
        : '<span>\u76ee\u524d\u6c92\u6709\u5019\u9078\u55AE\u963b\u64cb\u8cc7\u6599</span>';
}

function renderHistory() {
    const tbody = document.getElementById('history-body');
    const summary = document.getElementById('history-summary');
    tbody.innerHTML = '';
    const rows = filtered(historyData).slice(0, 80);
    const closedTradeTotalPnl = rows.reduce((sum, item) => {
        const info = item.info || {};
        return sum + Number(item.realizedPnl || info.realizedPnl || 0);
    }, 0);
    if (summary) {
        summary.innerHTML = `
            <div class="summary-card">
                <span>已平倉筆數</span>
                <strong>${rows.length}</strong>
            </div>
            <div class="summary-card">
                <span>已平倉合計</span>
                <strong class="${closedTradeTotalPnl >= 0 ? 'gain' : 'loss'}">${signed(closedTradeTotalPnl, 4)}</strong>
            </div>
            <div class="summary-card">
                <span>本頁口徑</span>
                <strong>只看 closed trades</strong>
            </div>
        `;
    }
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
            <td class="${pnl >= 0 ? 'gain' : 'loss'}">${signed(pnl, 4)}<small>手續費 ${signed(fee, 4)} / 資金費 ${signed(funding, 4)}</small></td>
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
    const model = buildStrategyCardModel(currentStrategyFilter);
    const perf = model.perf;
    const opt = model.opt;
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
    const verTag = match ? match[0].toUpperCase() : 'V13';
    const pnlText = `${pnlVal >= 0 ? '+' : ''}${pnlVal.toFixed(2)} USDT`;
    const pctText = `${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%`;

    document.getElementById('curve-label').textContent = `${verTag} 累積盈虧 ${pnlText} (${pctText})`;
    document.getElementById('curve-label').setAttribute('x', Math.max(60, Math.min(520, x - 28)));
    document.getElementById('curve-label').setAttribute('y', isDrawdown ? 174 : 28);
    
    const startLabel = document.getElementById('progress-start-label');
    const targetLabel = document.getElementById('progress-target-label');
    const titleLabel = document.getElementById('growth-title');
    if (startLabel) startLabel.textContent = `${money(dashboardCapital.start ?? START_EQUITY)} USDT`;
    if (targetLabel) targetLabel.textContent = `${money(dashboardCapital.target ?? TARGET_EQUITY)} USDT`;
    if (titleLabel) titleLabel.textContent = `${verTag} 累積盈虧曲線`;
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalPnl = Number(capital.cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = metrics.activePnl;
    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源: ${capital.strategy_unrealized_source || 'report.active_pnl'}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);

    const capitalChange = capitalPnl;
    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        capitalChangeEl.textContent = `${capitalChange >= 0 ? '+' : ''}${money(capitalChange)}`;
        capitalChangeEl.className = capitalChange >= 0 ? 'gain' : 'loss';
        capitalChangeEl.title = `累積盈虧來源: ${capital.cumulative_source || 'unknown'}`;
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = `V13 累積盈虧 (${capital.cumulative_source || 'unknown'})`;

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct) ? Number(capital.goal_progress_pct) : (targetProfitGoal !== 0 ? (capitalPnl / targetProfitGoal) * 100 : 0);
    updateProgressCurve(capitalPnl, signedProgress);
    const curveLabel = document.getElementById('curve-label');
    if (curveLabel) {
        curveLabel.textContent = `V13 累積盈虧 ${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)} USDT (${signedProgress >= 0 ? '+' : ''}${signedProgress.toFixed(2)}%)`;
    }
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = 'V13 累積盈虧曲線';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '掃描中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>實際持倉</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選訊號</strong></div>
            <div><span>${money(activePnl)}</span><strong>浮動盈虧</strong></div>
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
        const protectionVerified = trade.exchange_protection_verified === true || String(trade.exchange_protection_verified || '').toLowerCase() === 'true';
        const protectionFailed = trade.protection_status === 'failed' || trade.trailing_stage === 'protection_failed' || (isActive && trade.protection_status === 'confirmed' && !protectionVerified);
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
        const response = await requestJson('/api/trades', { cache: 'no-store' });
        if (!response.ok) throw new Error(`API ${response.status}`);
        const data = await response.json();
        if (data.error) console.warn('api_trades fallback', data.error);
        dashboardSnapshotAt = data.snapshot_at || data.generated_at || dashboardSnapshotAt;
        dashboardSourceState.snapshotAt = dashboardSnapshotAt;
        currentTrades = Array.isArray(data.trades) ? data.trades : [];
        radarData = data.radar && typeof data.radar === 'object' ? data.radar : {};
        runtimeStatus = data.runtime && typeof data.runtime === 'object' ? data.runtime : runtimeStatus;
        renderRuntimeStatusV2();
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
        renderRuntimeStatusV2();
        
        accountData = data.account && typeof data.account === 'object' ? data.account : {};
        if (data.capital && typeof data.capital === 'object') {
            accountData.capital = data.capital;
            dashboardCapital = data.capital;
        }
        profiles = data.profiles && typeof data.profiles === 'object' ? data.profiles : profiles;
        strategyStats = data.strategy_stats && typeof data.strategy_stats === 'object' ? data.strategy_stats : strategyStats;
        performanceData = data.performance && typeof data.performance === 'object' ? data.performance : performanceData;
        optimizerData = data.optimizer && typeof data.optimizer === 'object' ? data.optimizer : optimizerData;
        reportData = data.report && typeof data.report === 'object' ? data.report : reportData;
        entryEfficiencyData = data.entry_efficiency && typeof data.entry_efficiency === 'object' ? data.entry_efficiency : {};
        uiMetricsData = data.ui_metrics && typeof data.ui_metrics === 'object' ? data.ui_metrics : {};
        marketRouterData = data.market_router && typeof data.market_router === 'object' ? data.market_router : {};
        if (data.health_check && typeof data.health_check === 'object') {
            healthCheckData = data.health_check;
        }
        refreshSourceBadges();

        // Update Performance / Rehab Learning metadata (Version and Date range)
        const metaEl = document.getElementById('performance-metadata');
        if (metaEl) {
            const ver = data.strategy_version || '--';
            currentStrategyVersion = ver;
            let dateStr = '無歷史交易';
            const zeroStart = data.zero_start && typeof data.zero_start === 'object' ? data.zero_start : {};
            const accountSource = data.account?.source || accountData.source || '-';
            const snapshotAt = data.snapshot_at || data.generated_at || dashboardSnapshotAt || '-';
            if (data.journal_start && data.journal_end) {
                const formatTime = (ts) => {
                    const d = new Date(ts);
                    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
                };
                dateStr = `${formatTime(data.journal_start)} 至 ${formatTime(data.journal_end)}`;
            }
            const zeroStartLabel = zeroStart.zero_start_mode ? '零起點啟用' : '零起點關閉';
            const resetAt = zeroStart.reset_at ? new Date(zeroStart.reset_at).toLocaleString() : '-';
            metaEl.textContent = `版本 ${ver}｜${zeroStartLabel}｜快照 ${snapshotAt}｜來源 ${zhText(accountSource)}｜重置 ${resetAt}｜範圍 ${dateStr}`;
        }

        const bannerState = document.getElementById('version-banner-state');
        const bannerReset = document.getElementById('version-banner-reset');
        const bannerNode = document.getElementById('version-banner-node');
        const banner = data.zero_start && typeof data.zero_start === 'object' ? data.zero_start : {};
        if (bannerState) {
            bannerState.textContent = banner.zero_start_mode
                ? '本機乾淨訓練資料已啟用'
                : '零起點設定檔未啟用或不存在';
        }
        if (bannerReset) {
            bannerReset.textContent = `重置時間：${banner.reset_at ? new Date(banner.reset_at).toLocaleString() : '-'}`;
        }
        if (bannerNode) {
            bannerNode.textContent = `節點：${banner.node_name || runtimeStatus.node_name || '-'}`;
        }

        updateOverview();
        renderBotReport();
        renderEngineHeartbeat();
        renderModeCards();
        renderStrategyInfo();
        renderPerformance();
        renderTrades();
        renderEntryEfficiency();
        renderRadar();
        renderHealthCheck();
        
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
        const response = await requestJson('/api/history', { cache: 'no-store' });
        const data = await response.json();
        historyData = Array.isArray(data.history) ? data.history : [];
        refreshSourceBadges();
        renderHistory();
    } catch (error) {
        console.error('fetchHistory failed', error);
    }
}

async function fetchIntelligence() {
    try {
        const response = await requestJson('/api/intelligence', { cache: 'no-store' });
        const data = await response.json();
        profiles = data.profiles && typeof data.profiles === 'object' ? data.profiles : profiles;
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
        const s = normalizedEngineBucket(t);
        engineActive[s] = (engineActive[s] || 0) + 1;
        enginePnl[s] = (enginePnl[s] || 0) + Number(t.pnl || 0);
    });

    // Count signals (potential) per engine
    const engineSignals = {};
    currentTrades.filter(t => t.status === 'potential').forEach(t => {
        const s = normalizedEngineBucket(t);
        engineSignals[s] = (engineSignals[s] || 0) + 1;
    });

    // Win rate from strategyStats
    const engines = ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'];
    container.innerHTML = engines.map(name => {
        const meta = ENGINE_META[name] || { icon: '•', desc: name, color: '#888' };
        const model = buildStrategyCardModel(name);
        const stats = model.stats;
        const perf = model.perf;
        const opt = model.opt;
        const active = model.liveTrades.length;
        const signals = model.candidateTrades.length;
        const pnl = model.livePnl;
        const wr = model.winRate;
        const conf = opt.capital_mult != null ? opt.capital_mult.toFixed(2) : (stats.confidence != null ? stats.confidence.toFixed(2) : '1.00');
        const verdict = verdictLabel(model.verdict);
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
                const reason = firstRadar.trigger_reason || firstRadar.block_reason || '掃描中';
                detailedWaitingReason = `<div style="color: var(--muted); font-size: 10px; margin-top: 4px; border-left: 2px solid var(--line); padding-left: 4px;">⏳ 等待原因：${escapeHtml(zhReason(reason))} (${escapeHtml(firstRadar.symbol)})</div>`;
            } else {
                detailedWaitingReason = `<div style="color: var(--soft); font-size: 10px; margin-top: 4px;">⏳ 掃描中，目前無合適諧波區間</div>`;
            }
        }

        // Active trade stage summary
        const activeTrades = model.liveTrades;
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

function renderPerformance() {
    const tbody = document.getElementById('performance-body');
    if (!tbody) return;
    tbody.innerHTML = '';

    Object.keys(profiles || {}).forEach((name) => {
        if (currentStrategyFilter !== 'All' && name !== currentStrategyFilter) return;

        const model = buildStrategyCardModel(name);
        const perf = model.perf || {};
        const opt = model.opt || {};
        const liveCount = model.liveTrades?.length || 0;
        const candidateCount = model.candidateTrades?.length || 0;
        const livePnl = Number(model.livePnl || 0);
        const pf = Number(perf.profit_factor || 0);
        const exp = Number(perf.expectancy || 0);
        const stateLabel = optimizerLabel(opt);
        const tunedAtr = perf.tuned_sl_atr ? `ATR 調整: ${perf.tuned_sl_atr}` : '';
        const confidenceText = perf.confidence ? `AI 權重: ${perf.confidence}x` : '';
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>
                <strong>${strategyLabel(name)}</strong>
                <small>權重 ${perf.weight ?? '1.0'}x / 健康度 ${perf.health_score ?? '-'} / ${model.tierLabel || '-'}</small>
            </td>
            <td>
                ${liveCount} / ${candidateCount}
                <small>${verdictLabel(model.verdict || perf.verdict || 'learning')}</small>
            </td>
            <td class="${livePnl >= 0 ? 'gain' : 'loss'}">
                ${money(livePnl)}
                <small>同快照即時浮盈</small>
            </td>
            <td>
                ${perf.sample || 0} / ${perf.win_rate == null ? '-' : pct(perf.win_rate, 1)}
                <small>訓練樣本 / 勝率</small>
            </td>
            <td class="${pf >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</td>
            <td>
                <span class="gain">${money(perf.avg_win)}</span> / <span class="loss">${money(perf.avg_loss)}</span>
            </td>
            <td class="${exp >= 0 ? 'gain' : 'loss'}">${money(exp)}</td>
            <td>
                ${verdictBadge(perf.verdict)}
                <div style="font-size: 10px; color: #a1a1aa; margin-top: 4px; line-height: 1.3;">
                    狀態 ${stateLabel}<br>
                    ${tunedAtr}${tunedAtr && confidenceText ? ' | ' : ''}${confidenceText}
                    ${perf.max_consecutive_losses != null ? `<br>連虧 ${perf.max_consecutive_losses}` : ''}
                    ${perf.max_drawdown != null ? `<br>回撤 ${money(perf.max_drawdown)}` : ''}
                </div>
            </td>
        `;
        tbody.appendChild(row);
    });
}

function renderHealthCheck() {
    const summary = document.getElementById('health-summary');
    const blocks = document.getElementById('health-blocks');
    const detail = document.getElementById('health-detail');
    const stateEl = document.getElementById('health-check-state');
    if (!summary || !blocks || !detail || !stateEl) return;

    const model = buildHealthCheckModel();
    const data = model.data || {};
    const counts = model.counts || {};
    const liveCounts = model.liveCounts || {};
    const sessionCounts = model.sessionCounts || {};
    const status = String(data.status || 'warning').toLowerCase();
    const score = Number(data.score);
    const runtime = data.runtime || {};
    const version = data.strategy_version || currentStrategyVersion || 'v13';
    const zeroStart = data.zero_start || {};
    const snapshotAt = data.snapshot_at || data.generated_at || dashboardSnapshotAt || '-';
    const runtimeLabel = runtime.run_mode === 'live' ? '實盤' : (runtime.run_mode === 'demo' ? '模擬實盤' : '自動');

    stateEl.textContent = `${healthStatusLabel(status)} / 分數 ${Number.isFinite(score) ? score.toFixed(0) : '-'}`;

    summary.innerHTML = `
        <div class="health-card">
            <span>即時狀態</span>
            <strong class="${healthStatusClass(status)}">${healthStatusLabel(status)}</strong>
            <small>${escapeHtml(zhText(data.health_summary?.message || '等待檢查'))}</small>
        </div>
        <div class="health-card">
            <span>即時風險</span>
            <strong class="${liveCounts.badTrades > 0 ? 'loss' : 'gain'}">${liveCounts.badTrades ?? 0}</strong>
            <small>${liveCounts.activeTrades ?? 0} 個持倉 / ${counts.protection_warnings ?? 0} 個警告</small>
        </div>
        <div class="health-card">
            <span>執行狀態</span>
            <strong class="${runtime.run_mode === 'live' ? 'critical' : (runtime.run_mode === 'demo' ? 'warning' : 'good')}">${runtimeLabel}</strong>
            <small>${escapeHtml(runtime.node_name || '-')} / ${escapeHtml(snapshotAt)}</small>
        </div>
        <div class="health-card">
            <span>訓練統計</span>
            <strong class="${sessionCounts.trainingIssues > 0 ? 'loss' : 'gain'}">${sessionCounts.trainingIssues ?? 0}</strong>
            <small>${counts.verified_rows ?? 0} 已驗證 / ${counts.quarantined_rows ?? 0} 隔離 / ${counts.version_mismatch_rows ?? 0} 版本不符</small>
        </div>
    `;

    blocks.innerHTML = `
        <div class="health-block">
            <div class="health-block-title">
                <strong>即時異常</strong>
                <span>${counts.bad_trades ?? 0} 筆</span>
            </div>
            <div class="health-list">
                ${renderHealthList(data.bad_trades || [], '即時持倉異常')}
            </div>
        </div>
        <div class="health-block">
            <div class="health-block-title">
                <strong>訓練異常</strong>
                <span>${counts.training_issues ?? 0} 筆</span>
            </div>
            <div class="health-list">
                ${renderHealthList(data.abnormal_training_rows || [], '訓練資料異常')}
            </div>
        </div>
    `;

    detail.innerHTML = `
        <div class="health-detail-card">
            <h3>即時狀態</h3>
            <span class="hint">同一個快照下的持倉、警告與執行環境</span>
            <div class="health-tags">
                <span class="health-tag ${healthStatusClass(status)}">${healthStatusLabel(status)}</span>
                <span class="health-tag">${runtimeLabel}</span>
                <span class="health-tag">節點 ${escapeHtml(runtime.node_name || '-')}</span>
                <span class="health-tag">持倉 ${liveCounts.activeTrades ?? 0}</span>
                <span class="health-tag">警告 ${counts.protection_warnings ?? 0}</span>
            </div>
            <span class="hint">${escapeHtml(snapshotAt)}</span>
        </div>
        <div class="health-detail-card">
            <h3>訓練統計</h3>
            <span class="hint">驗證、隔離與版本一致性</span>
            <div class="health-tags">
                <span class="health-tag">已驗證 ${counts.verified_rows ?? 0}</span>
                <span class="health-tag ${sessionCounts.trainingIssues > 0 ? 'warning' : 'good'}">訓練異常 ${sessionCounts.trainingIssues ?? 0}</span>
                <span class="health-tag">隔離 ${counts.quarantined_rows ?? 0}</span>
                <span class="health-tag">版本不符 ${counts.version_mismatch_rows ?? 0}</span>
                <span class="health-tag ${zeroStart.zero_start_mode ? 'good' : 'warning'}">Zero-start ${zeroStart.zero_start_mode ? '已啟用' : '未啟用'}</span>
            </div>
            <span class="hint">${escapeHtml(version)}</span>
        </div>
    `;
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
        const response = await requestJson('/api/git-pull', {
            cache: 'no-store',
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
        const response = await requestJson('/api/reset-optimizer', {
            cache: 'no-store',
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

async function resetTraining() {
    if (!confirm('這會備份目前所有訓練資料、optimizer 與 cycle state，然後把本機訓練完全重置為 0。確定要繼續嗎？')) {
        return;
    }

    const btn = document.getElementById('reset-training-btn');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.innerHTML = '<span>重置訓練中...</span>';

    try {
        const response = await requestJson('/api/reset-training', {
            cache: 'no-store',
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
            alert(`重置訓練失敗: ${data.message || '未知錯誤'}`);
        }
    } catch (err) {
        alert(`重置訓練失敗: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = originalText;
        }
    }
}

async function resetTraining() {
    if (!confirm('確定要重置訓練資料嗎？系統會先備份 active trades / journal / optimizer / cycle state，然後從 0 重新累積。請先確認 OKX 異常倉位已處理。')) {
        return;
    }

    const btn = document.getElementById('reset-training-btn');
    if (!btn) return;

    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.style.opacity = '0.6';
    btn.innerHTML = '<span>重置訓練中...</span>';

    try {
        const response = await requestJson('/api/reset-training', {
            cache: 'no-store',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        if (response.ok && data.success) {
            alert(data.message || '訓練資料已重新歸零。');
            location.reload();
        } else {
            alert(`重置訓練失敗：${data.message || '未知錯誤'}`);
        }
    } catch (err) {
        alert(`重置訓練失敗：${err.message}`);
    } finally {
        btn.disabled = false;
        btn.style.opacity = '1';
        btn.innerHTML = originalText;
    }
}

async function depositDemoAsset() {
    const btn = document.getElementById('deposit-demo-btn');
    const originalText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.disabled = true;
        btn.style.opacity = '0.6';
        btn.innerHTML = '<span>💵 正在充值...</span>';
    }

    try {
        const response = await requestJson('/api/deposit-demo', {
            cache: 'no-store',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        alert(data.message);
        if (response.ok && data.success) {
            location.reload();
        }
    } catch (err) {
        alert(`連接伺服器失敗: ${err.message}`);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.style.opacity = '1';
            btn.innerHTML = originalText;
        }
    }
}

function buildStrategyCardModel(name) {
    const { liveModes, weakModes } = getUnifiedReportModes();
    const reportModes = new Map([...liveModes, ...weakModes].map((item) => [item.strategy, item]));
    const reportMode = reportModes.get(name) || {};
    const stats = strategyStats[name] || {};
    const perf = performanceData[name] || {};
    const opt = optimizerData[name] || {};
    const liveTrades = currentTrades.filter((trade) => trade.status === 'active' && normalizedEngineBucket(trade) === name);
    const candidateTrades = currentTrades.filter((trade) => trade.status === 'potential' && normalizedEngineBucket(trade) === name);
    const livePnl = liveTrades.reduce((sum, trade) => sum + Number(trade.pnl || 0), 0);
    const cumulativePnl = Number(stats.pnl || perf.total_pnl || 0);
    const cumulativePnlSource = perf.pnl_source_label || '來源：已驗證歷史 / alphaPnl';
    const winRate = (perf.win_rate == null || perf.total_trades === 0) ? '-' : pct(perf.win_rate, 1);
    const verdict = perf.verdict || stats.verdict || 'learning';
    const tierLabel = reportMode.tier ? modeTierLabel(reportMode.tier) : modeTierLabel(opt.state === 'exploit' || opt.state === 'steady' ? 'live_calibration' : 'watch');
    const reasonText = reportMode.reason || verdictDetail(perf);
    return {
        reportMode,
        stats,
        perf,
        opt,
        liveTrades,
        candidateTrades,
        livePnl,
        cumulativePnl,
        cumulativePnlSource,
        winRate,
        verdict,
        tierLabel,
        reasonText,
    };
}

function updateOverview() {
    const metrics = getUnifiedReportMetrics();
    const capital = metrics.capital || {};
    const equity = Number(capital.equity ?? accountData.usdtEq ?? accountData.usdtAvail ?? 0);
    const capitalSnapshotAvailable = Boolean(metrics.capitalSnapshotAvailable ?? capital.account_snapshot_available ?? capital.account_layer_pnl != null);
    const capitalPnl = capitalSnapshotAvailable ? Number(capital.account_layer_pnl ?? capital.cumulative_pnl ?? 0) : null;
    const sessionPnl = Number(capital.session_cumulative_pnl ?? capital.pnl_from_start ?? 0);
    const activePnl = Number(metrics.activePnl || 0);
    const activePnlSource = metrics.activePnlSource || capital.strategy_unrealized_source || 'OKX / 活倉快照';
    const capitalSource = metrics.capitalSource || capital.account_layer_source || capital.cumulative_source || 'OKX / 帳戶快照';

    const pnlEl = document.getElementById('total-profit');
    if (pnlEl) {
        pnlEl.textContent = `${activePnl >= 0 ? '+' : ''}${money(activePnl)}`;
        pnlEl.className = `value ${activePnl >= 0 ? 'gain' : 'loss'}`;
        pnlEl.title = `未實現損益來源：${activePnlSource}`;
    }
    const totalEquityEl = document.getElementById('total-equity');
    const availEl = document.getElementById('usdt-avail');
    if (totalEquityEl) totalEquityEl.textContent = money(equity);
    if (availEl) availEl.textContent = money(accountData.usdtAvail ?? capital.equity ?? 0);
    setMetricSource('total-equity', `來源：${capitalSource}`);
    setMetricSource('usdt-avail', `來源：${capitalSource}`);
    setMetricSource('total-profit', `來源：${activePnlSource}`);

    const capitalChangeEl = document.getElementById('capital-change');
    if (capitalChangeEl) {
        if (capitalPnl == null || !Number.isFinite(capitalPnl)) {
            capitalChangeEl.textContent = '--';
            capitalChangeEl.className = 'value';
            capitalChangeEl.title = 'OKX 帳戶快照不可用，未以策略推算值冒充帳戶層';
        } else {
            capitalChangeEl.textContent = `${capitalPnl >= 0 ? '+' : ''}${money(capitalPnl)}`;
            capitalChangeEl.className = capitalPnl >= 0 ? 'gain' : 'loss';
            capitalChangeEl.title = `帳戶層來源：${capitalSource}`;
        }
    }
    const capitalLabel = document.getElementById('version-pnl-label');
    if (capitalLabel) capitalLabel.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧（帳戶層）' : 'V13 累積盈虧（帳戶快照不可用）';
    setMetricSource('capital-change', capitalSnapshotAvailable ? `來源：${capitalSource}` : '來源：OKX 帳戶快照不可用 / 只顯示 Session 推算');

    const targetProfitGoal = Number((capital.target ?? TARGET_EQUITY) - (capital.start ?? START_EQUITY));
    const signedProgress = Number.isFinite(capital.goal_progress_pct)
        ? Number(capital.goal_progress_pct)
        : (targetProfitGoal !== 0 ? (sessionPnl / targetProfitGoal) * 100 : 0);
    const curvePnl = capitalSnapshotAvailable ? Number(capitalPnl ?? 0) : sessionPnl;
    updateProgressCurve(curvePnl, signedProgress);
    const growthTitle = document.getElementById('growth-title');
    if (growthTitle) growthTitle.textContent = capitalSnapshotAvailable ? 'V13 累積盈虧曲線（帳戶層）' : 'V13 Session 推算曲線（非帳戶層）';

    const verdictEl = document.getElementById('bot-verdict');
    if (verdictEl) verdictEl.textContent = zhText(metrics.verdict || '觀察中');
    const summaryEl = document.getElementById('operator-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div><span>${metrics.activeCount}</span><strong>持倉中</strong></div>
            <div><span>${metrics.potentialCount}</span><strong>候選單</strong></div>
            <div><span>${money(activePnl)}</span><strong>活倉浮動盈虧</strong></div>
        `;
    }
}
function renderModeCards() {
    const container = document.getElementById('mode-cards');
    if (!container) return;
    container.innerHTML = '';
    Object.entries(profiles).forEach(([name, profile]) => {
        const model = buildStrategyCardModel(name);
        const perf = model.perf;
        const opt = model.opt;
        const liveTrades = model.liveTrades;
        const candidateTrades = model.candidateTrades;
        const livePnl = model.livePnl;
        const pnl = model.cumulativePnl;
        const pnlSource = model.cumulativePnlSource || '來源：已驗證歷史 / alphaPnl';
        const winRate = model.winRate;
        const verdict = model.verdict;
        const tierLabel = model.tierLabel;
        const reasonText = model.reasonText;
        const card = document.createElement('article');
        card.className = 'mode-card';
        card.innerHTML = `
            <div class="mode-card-head">
                <strong>${strategyLabel(name)}</strong>
                ${verdictBadge(verdict)}
            </div>
            <p>${tierLabel}</p>
            <div class="mode-stats">
                <div><span>持倉</span><strong class="${liveTrades.length > 0 ? 'gain' : ''}">${liveTrades.length}</strong></div>
                <div><span>候選</span><strong>${candidateTrades.length}</strong></div>
                <div><span>活倉浮動</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${money(livePnl)}</strong><small class="metric-source">來源：OKX / 活倉快照</small></div>
                <div><span>勝率</span><strong>${winRate}</strong></div>
                <div><span>期望值</span><strong class="${Number(perf.expectancy || 0) >= 0 ? 'gain' : 'loss'}">${money(perf.expectancy)}</strong></div>
                <div><span>PF</span><strong class="${Number(perf.profit_factor || 0) >= 1 ? 'gain' : 'loss'}">${perf.profit_factor ?? '-'}</strong></div>
            </div>
            <p class="mode-note">${escapeHtml(reasonText)}</p>
            <p class="mode-note cumulative-note">模式已實現盈虧 ${escapeHtml(signed(pnl, 1))}U<span class="metric-source-inline">${escapeHtml(pnlSource)}</span></p>
            <div class="rule-line">60U x 1.00 x ${Number(profile.margin_mult || 1).toFixed(2)} / SL ${profile.sl_atr}x ATR / TP ${profile.tp_atr}x ATR</div>
        `;
        container.appendChild(card);
    });
}
function renderEngineHeartbeat() {
    const container = document.getElementById('engine-heartbeat');
    if (!container) return;
    const engines = ['MacroSniper', 'MeanReversion', 'Contrarian', 'SqueezeHunter'];
    container.innerHTML = engines.map((name) => {
        const meta = ENGINE_META[name] || { icon: '•', desc: name, color: '#888' };
        const model = buildStrategyCardModel(name);
        const stats = model.stats;
        const perf = model.perf;
        const opt = model.opt;
        const active = model.liveTrades.length;
        const signals = model.candidateTrades.length;
        const livePnl = Number(model.livePnl || 0);
        const cumulativePnl = Number(model.cumulativePnl || 0);
        const cumulativePnlSource = model.cumulativePnlSource || '來源：已驗證歷史 / alphaPnl';
        const wr = model.winRate;
        const conf = opt.capital_mult != null ? opt.capital_mult.toFixed(2) : (stats.confidence != null ? stats.confidence.toFixed(2) : '1.00');
        const verdict = verdictLabel(model.verdict);
        const verdictColor = perf.state === 'exploit' ? '#22c55e' : perf.state === 'steady' ? '#60a5fa' : perf.state === 'pause' ? '#ef4444' : '#f59e0b';
        return `
        <div class="eng-card" style="border-top: 3px solid ${meta.color}">
            <div class="eng-head">
                <strong>${escapeHtml(meta.icon)} ${escapeHtml(strategyLabel(name))}</strong>
                <span class="eng-verdict" style="color:${verdictColor}">${escapeHtml(verdict)}</span>
            </div>
            <div class="eng-desc">${escapeHtml(meta.desc)}</div>
            <div class="eng-stats" style="grid-template-columns: repeat(5, 1fr);">
                <div><span>勝率</span><strong>${escapeHtml(wr)}</strong></div>
                <div><span>信心</span><strong>${escapeHtml(conf)}x</strong></div>
                <div><span>持倉</span><strong>${escapeHtml(active)} 筆</strong></div>
                <div><span>活倉浮動</span><strong class="${livePnl >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(livePnl, 1))}U</strong><small class="metric-source">來源：OKX / 活倉快照</small></div>
                <div><span>模式已實現</span><strong class="${cumulativePnl >= 0 ? 'gain' : 'loss'}">${escapeHtml(signed(cumulativePnl, 1))}U</strong><small class="metric-source">${escapeHtml(cumulativePnlSource)}</small></div>
            </div>
            <div class="eng-scan-status">${signals > 0 ? `<span class="eng-scanning">掃描中 ${signals} 個候選</span>` : `<span class="eng-idle">待命</span>`}</div>
        </div>`;
    }).join('');
}
function renderBotReport() {
    const box = document.getElementById('bot-report');
    if (!box) return;
    const { liveModes, weakModes } = getUnifiedReportModes();
    const metrics = getUnifiedReportMetrics();
    const activeCount = Number(metrics.activeCount || 0);
    const potentialCount = Number(metrics.potentialCount || 0);
    const activePnl = Number(metrics.activePnl || 0);
    const sessionActivePnl = Number(metrics.sessionActivePnl || 0);
    const sessionRealizedPnl = Number(metrics.sessionRealizedPnl || 0);
    const activePnlSource = metrics.activePnlSource || 'OKX / 活倉快照';
    const sessionRealizedSource = metrics.sessionRealizedSource || '已驗證歷史 / session alphaPnl';
    const verdict = zhText(metrics.verdict || '-');
    const serverTime = metrics.serverTime || '-';
    box.innerHTML = `
        <div class="health-summary">
            <div class="health-card">
                <span>狀態</span>
                <strong class="${activeCount > 0 ? 'warn' : 'good'}">${escapeHtml(verdict)}</strong>
                <small>${escapeHtml(serverTime)}</small>
            </div>
            <div class="health-card">
                <span>活倉浮動盈虧</span>
                <strong class="${activePnl >= 0 ? 'gain' : 'loss'}">${signed(activePnl)}</strong>
                <small>${activeCount} 持倉 / ${potentialCount} 候選</small>
                <small class="metric-source">來源：${escapeHtml(activePnlSource)}</small>
            </div>
            <div class="health-card">
                <span>Session 已實現</span>
                <strong class="${sessionRealizedPnl >= 0 ? 'gain' : 'loss'}">${signed(sessionRealizedPnl)}</strong>
                <small>Session 浮動 ${signed(sessionActivePnl)}</small>
                <small class="metric-source">來源：${escapeHtml(sessionRealizedSource)}</small>
            </div>
            <div class="health-card">
                <span>模式數</span>
                <strong class="${liveModes.length > 0 ? 'gain' : 'loss'}">${liveModes.length} / ${weakModes.length}</strong>
                <small>活躍 / 觀察</small>
            </div>
        </div>
    `;
}
