param(
    [string]$ProfileName = 'okx-demo',
    [switch]$DemoMode = $true
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RootDir 'state'
$SnapshotPath = Join-Path $StateDir 'okx_live_snapshot.json'
$PositionsTextPath = Join-Path $StateDir 'okx_live_positions_snapshot.txt'
$AccountTextPath = Join-Path $StateDir 'okx_live_account_snapshot.txt'

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Parse-OkxPositions {
    param([string]$Text)

    function Convert-InstIdToSymbol {
        param([string]$InstId)
        $raw = ([string]$InstId).Trim().ToUpperInvariant()
        if (-not $raw) { return '' }
        if ($raw.EndsWith('-USDT-SWAP')) { return $raw.Replace('-USDT-SWAP', 'USDT') }
        if ($raw.EndsWith('-USD-SWAP')) { return $raw.Replace('-USD-SWAP', 'USD') }
        return $raw
    }

    $rows = @()
    $headerSeen = $false
    foreach ($rawLine in ($Text -split "`r?`n")) {
        $line = $rawLine.Trim()
        if (-not $line) { continue }
        $lowered = $line.ToLowerInvariant()
        if ($lowered.StartsWith('instid') -and $lowered.Contains('avgpx') -and $lowered.Contains('uplratio')) {
            $headerSeen = $true
            continue
        }
        if (-not $headerSeen) { continue }
        if ($line.StartsWith('-') -or $lowered.StartsWith('environment:') -or $lowered.StartsWith('update available') -or $lowered.StartsWith('run:')) {
            continue
        }
        $parts = $line -split '\s{2,}|\t+'
        if ($parts.Count -lt 7) {
            $parts = $line -split '\s+'
        }
        if ($parts.Count -lt 7) { continue }
        $size = 0.0
        if (-not [double]::TryParse($parts[2], [ref]$size)) { continue }
        $instId = $parts[0]
        $direction = if ($size -lt 0) { 'short' } else { 'long' }
        $qty = [math]::Abs($size)
        $avgPx = [double]$parts[3]
        $upl = [double]$parts[4]
        $uplRatio = [double]$parts[5]
        $lever = $parts[6]
        $rows += [ordered]@{
            id = $instId
            posId = $instId
            instId = $instId
            symbol = Convert-InstIdToSymbol $instId
            raw_symbol = $instId
            side = $direction
            posSide = $direction
            direction = $direction
            status = 'active'
            source = 'okx_cli_demo'
            size = $qty
            contracts = $qty
            availPos = $qty
            avgPx = $avgPx
            entryPrice = $avgPx
            markPrice = $avgPx
            current = $avgPx
            upl = $upl
            unrealizedPnl = $upl
            pnl = $upl
            uplRatio = $uplRatio
            percentage = $uplRatio
            lever = $lever
            leverage = $lever
            initialMargin = 0.0
            notional = 0.0
            liquidationPrice = 0.0
            marginRatio = 0.0
            marginMode = 'cross'
            info = [ordered]@{
                instId = $instId
                side = $direction
                avgPx = $avgPx
                upl = $upl
                uplRatio = $uplRatio
                lever = $lever
                source = 'okx_cli_demo'
            }
        }
    }
    return $rows
}

function Parse-OkxBalance {
    param([string]$Text)

    $rows = @()
    $headerSeen = $false
    foreach ($rawLine in ($Text -split "`r?`n")) {
        $line = $rawLine.Trim()
        if (-not $line) { continue }
        $lowered = $line.ToLowerInvariant()
        if ($lowered.StartsWith('currency') -and $lowered.Contains('equity') -and $lowered.Contains('available')) {
            $headerSeen = $true
            continue
        }
        if (-not $headerSeen) { continue }
        if ($line.StartsWith('-') -or $lowered.StartsWith('environment:') -or $lowered.StartsWith('update available') -or $lowered.StartsWith('run:')) {
            continue
        }
        $parts = $line -split '\s{2,}|\t+'
        if ($parts.Count -lt 4) {
            $parts = $line -split '\s+'
        }
        if ($parts.Count -lt 4) { continue }
        $rows += [ordered]@{
            ccy = $parts[0]
            eq = $parts[1]
            avail = $parts[2]
            frozen = $parts[3]
        }
    }
    return $rows
}

function Invoke-OkxCli {
    param([string[]]$CliArgs)

    $cliPath = $env:OKX_CLI_PATH
    if (-not $cliPath) {
        $cliPath = 'C:\Users\User\AppData\Roaming\npm\okx.cmd'
    }

    $callArgs = @()
    if ($ProfileName) {
        $callArgs += '--profile'
        $callArgs += $ProfileName
    }
    if ($DemoMode) {
        $callArgs += '--demo'
    }
    $callArgs += $CliArgs

    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $cliPath @callArgs 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }

    $text = ($output | ForEach-Object { "$_" }) -join [Environment]::NewLine
    if ($exitCode -ne 0) {
        throw "okx cli returned exit code $exitCode. Output: $text"
    }
    return $text
}

$positionsText = Invoke-OkxCli -CliArgs @('swap', 'positions')
$balanceText = Invoke-OkxCli -CliArgs @('account', 'balance')

$positions = @(Parse-OkxPositions $positionsText)
$balance = @(Parse-OkxBalance $balanceText)
$usdtDetail = $balance | Where-Object { $_.ccy -eq 'USDT' } | Select-Object -First 1
if (-not $usdtDetail) {
    throw 'No USDT balance parsed from OKX CLI output; refusing to overwrite snapshots.'
}

$positionsText | Set-Content -LiteralPath $PositionsTextPath -Encoding UTF8
$balanceText | Set-Content -LiteralPath $AccountTextPath -Encoding UTF8

$accountSnapshot = [ordered]@{
    ccy = 'USDT'
    totalEq = [double]$usdtDetail.eq
    usdtEq = [double]$usdtDetail.eq
    usdtAvail = [double]$usdtDetail.avail
    eq = [double]$usdtDetail.eq
    avail = [double]$usdtDetail.avail
    frozen = [double]$usdtDetail.frozen
    source = 'okx_cli_demo'
}

$snapshot = [ordered]@{
    source = 'okx_cli_demo'
    synced_at = (Get-Date).ToString('s')
    account = $accountSnapshot
    positions = @($positions)
}

$snapshot | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $SnapshotPath -Encoding UTF8

Write-Host "[OK] Wrote live snapshot to $SnapshotPath"
Write-Host "[OK] Wrote positions text snapshot to $PositionsTextPath"
Write-Host "[OK] Wrote account text snapshot to $AccountTextPath"
Write-Host ("[OK] positions={0} usdtEq={1} usdtAvail={2}" -f $positions.Count, $usdtDetail.eq, $usdtDetail.avail)
