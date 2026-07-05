import re

with open('ui/app.js', 'r', encoding='utf-8') as f:
    original = f.read()

new_app_js = """let currentTrades = [];
let historyData = [];
let previousPnL = new Map();
let loops = 0;

// Chart Instances
let winRateChart = null;
let pnlBarChart = null;
let currentStrategyFilter = 'All';

// Initialize Charts
function initCharts() {
    const winCtx = document.getElementById('winRateChart').getContext('2d');
    const barCtx = document.getElementById('pnlBarChart').getContext('2d');
    
    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = 'Inter, -apple-system, sans-serif';

    winRateChart = new Chart(winCtx, {
        type: 'doughnut',
        data: {
            labels: ['獲利 (Wins)', '虧損 (Losses)'],
            datasets: [{
                data: [0, 0],
                backgroundColor: ['rgba(16, 185, 129, 0.8)', 'rgba(239, 68, 68, 0.8)'],
                borderColor: ['#0f172a', '#0f172a'],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '70%',
            plugins: {
                legend: { position: 'bottom', labels: { boxWidth: 12 } }
            }
        }
    });

    pnlBarChart = new Chart(barCtx, {
        type: 'bar',
        data: {
            labels: [],
            datasets: [{
                label: '單筆盈虧 (USDT)',
                data: [],
                backgroundColor: [],
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { grid: { color: 'rgba(255,255,255,0.05)' } },
                x: { display: false } // Hide individual trade labels to keep it clean
            },
            plugins: {
                legend: { display: false }
            }
        }
    });
}

// Strategy Analysis Engine
function updateStrategyDashboard() {
    // Filter Data by currentStrategyFilter
    let filteredHistory = historyData;
    let filteredTrades = currentTrades;
    
    if (currentStrategyFilter !== 'All') {
        filteredHistory = historyData.filter(h => (h.strategy || 'Manual') === currentStrategyFilter);
        filteredTrades = currentTrades.filter(t => (t.strategy || 'Manual') === currentStrategyFilter);
    }
    
    // Calculate KPIs
    let wins = 0;
    let losses = 0;
    let totalRealized = 0;
    let pnlHistory = [];
    
    filteredHistory.forEach(h => {
        const pnl = parseFloat(h.realizedPnl);
        totalRealized += pnl;
        pnlHistory.push(pnl);
        if (pnl >= 0) wins++;
        else losses++;
    });
    
    const activeCount = filteredTrades.filter(t => t.status === 'active').length;
    const totalCount = wins + losses;
    const winRate = totalCount > 0 ? ((wins / totalCount) * 100).toFixed(1) : 0;
    
    // Update DOM Cards
    const pnlEl = document.getElementById('strat-pnl');
    pnlEl.textContent = (totalRealized >= 0 ? '+$' : '-$') + Math.abs(totalRealized).toFixed(2);
    pnlEl.className = 'metric-value ' + (totalRealized >= 0 ? 'positive' : 'negative');
    
    document.getElementById('strat-winrate').textContent = totalCount > 0 ? `${winRate}%` : '--%';
    document.getElementById('strat-counts').textContent = `${totalCount} / ${activeCount}`;
    
    // Update Charts
    if (winRateChart && pnlBarChart) {
        winRateChart.data.datasets[0].data = [wins, losses];
        winRateChart.update();
        
        pnlBarChart.data.labels = pnlHistory.map((_, i) => `Trade ${i+1}`);
        pnlBarChart.data.datasets[0].data = pnlHistory;
        pnlBarChart.data.datasets[0].backgroundColor = pnlHistory.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.6)' : 'rgba(239, 68, 68, 0.6)');
        pnlBarChart.update();
    }
}

// Attach Strategy Button Listeners
document.querySelectorAll('.strat-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.strat-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentStrategyFilter = e.target.dataset.strat;
        updateStrategyDashboard();
    });
});


async function fetchTrades() {
    try {
        const response = await fetch('/api/trades');
        const data = await response.json();
        currentTrades = data.trades;
        
        loops++;
        
        updateOverviewCards(data.trades, data.account, data.radar);
        renderRadar(data.radar);
        
        const activeFilter = document.querySelector('.tab.active').dataset.filter;
        renderTable(activeFilter);
        
        fetchHistory(); // fetch history alongside trades
    } catch (error) {
        console.error('Failed to fetch data:', error);
    }
}

async function fetchHistory() {
    try {
        const response = await fetch('/api/history');
        const data = await response.json();
        historyData = data.history;
        renderHistoryTable(historyData);
        updateStrategyDashboard(); // Update charts when data arrives
    } catch (error) {
        console.error('Failed to fetch history:', error);
    }
}

function getTrendPill(tf, trend) {
    if (!trend) return '';
    const isBull = trend === 'bull' || trend === 'bullish';
    const tClass = isBull ? 'trend-bull' : (trend === 'bear' || trend === 'bearish' ? 'trend-bear' : '');
    const tText = isBull ? '多' : (trend === 'bear' || trend === 'bearish' ? '空' : '平');
    return `<span class="pill ${tClass}">${tf} ${tText}</span>`;
}

// Render Market Scanner Radar
function renderRadar(radarData) {
    const tbody = document.getElementById('radar-body');
    tbody.innerHTML = '';
    
    radarData.forEach(item => {
        const tr = document.createElement('tr');
        
        let trendsHtml = '';
        if (item.trends) {
            trendsHtml = `
                <div class="pill-row">
                    ${getTrendPill('1H', item.trends['1h'])}
                    ${getTrendPill('4H', item.trends['4h'])}
                    ${getTrendPill('1D', item.trends['1d'])}
                </div>
            `;
        } else {
            trendsHtml = getTrendPill('4H', item.trend);
        }

        tr.innerHTML = `
            <td class="symbol-col">${item.symbol}</td>
            <td>
                <div class="mtf-group">
                    ${trendsHtml}
                    <span class="pill" style="color: ${item.rsi > 70 ? 'var(--loss)' : (item.rsi < 30 ? 'var(--profit)' : 'var(--text-secondary)')}; width: fit-content; margin-top: 4px;">RSI ${item.rsi}</span>
                </div>
            </td>
            <td>
                <div style="display: flex; justify-content: space-between; font-size: 0.8rem; font-weight: 500;">
                    <span style="color: ${item.score > 80 ? 'var(--warning)' : 'var(--text-secondary)'}">${item.pattern !== 'None' ? item.pattern : 'Scanning'}</span>
                    <span>${item.score}%</span>
                </div>
                <div class="radar-score-bar">
                    <div class="radar-score-fill ${item.score > 80 ? 'hot' : ''}" style="width: ${item.score}%"></div>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Render Active Positions Table
function renderTable(filter = 'all') {
    const tbody = document.getElementById('trades-body');
    tbody.innerHTML = '';

    const filtered = currentTrades.filter(t => {
        if (filter === 'active') return t.status === 'active';
        if (filter === 'potential') return t.status === 'potential';
        return true;
    });

    filtered.forEach(t => {
        const tr = document.createElement('tr');
        
        const statusMap = {
            'active': { class: 'badge-active', text: '真實持倉' },
            'potential': { class: 'badge-potential', text: '等待進場' },
            'closed': { class: 'badge-closed', text: '已平倉' }
        };

        const dirClass = t.direction === 'long' ? 'badge-long' : 'badge-short';
        const dirText = t.direction === 'long' ? '做多 (LONG)' : '做空 (SHORT)';
        
        const rsiColor = t.rsi_on_entry > 70 ? 'var(--loss)' : (t.rsi_on_entry < 30 ? 'var(--profit)' : 'var(--text-secondary)');

        // MTF rendering
        let trendsHtml = '';
        if (t.trends) {
            trendsHtml = `
                <div class="pill-row">
                    ${getTrendPill('1H', t.trends['1h'])}
                    ${getTrendPill('4H', t.trends['4h'])}
                    ${getTrendPill('1D', t.trends['1d'])}
                </div>
            `;
        } else {
            trendsHtml = getTrendPill('4H', t.htf_trend);
        }

        // Animation logic
        let pnlClass = t.pnl >= 0 ? 'text-profit' : 'text-loss';
        let rowClass = '';
        if (t.status === 'active') {
            const prev = previousPnL.get(t.id);
            if (prev !== undefined && prev !== t.pnl) {
                rowClass = 'flash';
            }
            previousPnL.set(t.id, t.pnl);
        }

        const pnlText = t.status === 'potential' ? '-' : (t.pnl >= 0 ? '+' : '') + t.pnl.toFixed(2) + (t.percentage ? ` (${t.percentage > 0 ? '+' : ''}${t.percentage.toFixed(2)}%)` : '');
        
        const leverageStr = t.leverage ? `${t.leverage}x` : '-';
        const marginStr = t.initialMargin ? `$${parseFloat(t.initialMargin).toFixed(2)}` : '-';
        const notionalStr = t.notional ? `$${parseFloat(t.notional).toFixed(2)}` : '-';
        const liqPriceStr = t.liquidationPrice ? parseFloat(t.liquidationPrice).toFixed(4) : '-';

        tr.className = rowClass;
        tr.innerHTML = `
            <td class="symbol-col">
                <div style="font-size: 1rem; font-weight: 700;">${t.symbol}</div>
                <span class="badge ${dirClass}" style="margin-top: 4px;">${dirText}</span>
            </td>
            <td><span class="badge" style="background: var(--bg-card-hover); color: var(--text-accent); border: 1px solid rgba(56, 189, 248, 0.3);">${t.strategy || 'Manual'}</span></td>
            <td>
                <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-primary); margin-bottom: 6px;">${t.pattern}</div>
                <div class="mtf-group">
                    ${trendsHtml}
                    <span class="pill" style="color: ${rsiColor}; width: fit-content; margin-top: 2px;">RSI ${t.rsi_on_entry || '--'}</span>
                </div>
            </td>
            <td><span class="badge ${statusMap[t.status].class}">${statusMap[t.status].text}</span></td>
            <td>
                <div class="mono" style="font-size: 0.85rem;">保證金: ${marginStr}</div>
                <div class="mono" style="color: var(--text-secondary); font-size: 0.75rem;">槓桿: ${leverageStr}</div>
                <div class="mono" style="color: var(--text-secondary); font-size: 0.75rem;">名目: ${notionalStr}</div>
            </td>
            <td>
                <div class="mono" style="color: var(--text-secondary); font-size: 0.8rem;">進場: ${t.entry.toFixed(4)}</div>
                <div class="mono bold" style="font-size: 0.9rem;">當前: ${t.current.toFixed(4)}</div>
            </td>
            <td>
                <div class="mono" style="color: var(--warning); font-size: 0.75rem;">強平: ${liqPriceStr}</div>
                <div class="mono" style="color: var(--profit); font-size: 0.75rem;">停利: ${t.tp1 ? t.tp1.toFixed(4) : '-'}</div>
                <div class="mono" style="color: var(--loss); font-size: 0.75rem;">停損: ${t.sl.toFixed(4)}</div>
            </td>
            <td class="mono bold ${pnlClass}" style="font-size: 1rem;">${pnlText}</td>
        `;
        tbody.appendChild(tr);
    });
}

function renderHistoryTable(historyData) {
    const tbody = document.getElementById('history-body');
    tbody.innerHTML = '';
    
    if (!historyData || historyData.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-secondary); padding: 1rem;">尚無平倉歷史</td></tr>';
        return;
    }

    historyData.forEach(h => {
        const tr = document.createElement('tr');
        const info = h.info;
        
        const isLong = info.direction === 'long';
        const dirClass = isLong ? 'badge-long' : 'badge-short';
        const dirText = isLong ? '做多' : '做空';
        
        const realPnl = parseFloat(h.realizedPnl);
        const pnlClass = realPnl >= 0 ? 'text-profit' : 'text-loss';
        const pnlSign = realPnl >= 0 ? '+' : '';
        
        const dateStr = new Date(h.timestamp).toLocaleString();
        
        tr.innerHTML = `
            <td class="symbol-col" style="font-weight: 600;">${h.symbol.replace(':USDT', '')}</td>
            <td><span class="badge" style="background: var(--bg-card-hover); color: var(--text-accent); border: 1px solid rgba(56, 189, 248, 0.3);">${h.strategy || 'Manual'}</span></td>
            <td>
                <span class="badge ${dirClass}">${dirText}</span>
                <span class="mono" style="font-size: 0.8rem; margin-left: 4px;">${info.lever}x</span>
            </td>
            <td class="mono">${h.entryPrice ? h.entryPrice.toFixed(4) : '-'}</td>
            <td class="mono">${h.lastPrice ? h.lastPrice.toFixed(4) : '-'}</td>
            <td class="mono bold ${pnlClass}">${pnlSign}${realPnl.toFixed(4)}</td>
            <td class="mono" style="color: var(--text-secondary); font-size: 0.8rem;">${parseFloat(info.fee).toFixed(4)}</td>
            <td class="mono" style="font-size: 0.8rem; color: var(--text-secondary);">${dateStr}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateOverviewCards(trades, account, radar) {
    let totalPnl = 0;
    
    trades.forEach(t => {
        if (t.status === 'active') {
            totalPnl += t.pnl;
        }
    });

    const profitEl = document.getElementById('total-profit');
    profitEl.textContent = (totalPnl >= 0 ? '+$' : '-$') + Math.abs(totalPnl).toFixed(2);
    profitEl.className = 'metric-value ' + (totalPnl >= 0 ? 'positive' : 'negative');

    if (account && account.totalEq > 0) {
        document.getElementById('total-equity').textContent = '$' + account.totalEq.toFixed(2);
        document.getElementById('usdt-avail').textContent = '$' + account.usdtAvail.toFixed(2);
    }
}

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        e.target.classList.add('active');
        renderTable(e.target.dataset.filter);
    });
});

// Init
window.addEventListener('DOMContentLoaded', () => {
    initCharts();
    fetchTrades();
    setInterval(fetchTrades, 5000);
});
"""

with open('ui/app.js', 'w', encoding='utf-8') as f:
    f.write(new_app_js)
print('Done writing app.js')
