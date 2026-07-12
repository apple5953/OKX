param(
    [string]$NodeName,
    [string]$RunMode,
    [switch]$SkipLaunch
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
Set-Location $RootDir

function Normalize-NodeName {
    param([string]$Value)
    if ($null -eq $Value) {
        $text = ''
    } else {
        $text = $Value.Trim()
    }
    $text = $text -replace '[^A-Za-z0-9._-]+', '-'
    $text = $text.Trim('.','_','-')
    return $text
}

function Normalize-RunMode {
    param([string]$Value)
    if ($null -eq $Value) {
        return ''
    }
    $text = $Value.Trim().ToLowerInvariant()
    switch ($text) {
        'auto' { return 'auto' }
        'mock' { return 'mock' }
        'demo' { return 'demo' }
        'live' { return 'live' }
        'simulation' { return 'mock' }
        'sim' { return 'mock' }
        'paper' { return 'mock' }
        'sandbox' { return 'demo' }
        'testnet' { return 'demo' }
        default { return '' }
    }
}

function Get-DefaultNodeName {
    $hostname = Normalize-NodeName $env:COMPUTERNAME
    if (-not $hostname) {
        $hostname = 'node'
    }
    $mac = $null
    try {
        $mac = Get-CimInstance Win32_NetworkAdapterConfiguration -Filter "IPEnabled = True" |
            Select-Object -First 1 -ExpandProperty MACAddress
    } catch {
        $mac = $null
    }
    $suffix = if ($mac) { (($mac -replace '[:\-]', '') -replace '[^A-Fa-f0-9]', '').Substring(0, [Math]::Min(6, (($mac -replace '[:\-]', '')).Length)) } else { '000000' }
    return ("{0}-{1}" -f $hostname.ToLower(), $suffix.ToLower())
}

$resolvedNodeName = Normalize-NodeName $NodeName
if (-not $resolvedNodeName) {
    $resolvedNodeName = Normalize-NodeName $env:OKX_NODE_NAME
}
if (-not $resolvedNodeName) {
    $resolvedNodeName = Normalize-NodeName $env:NODE_NAME
}
if (-not $resolvedNodeName) {
    $resolvedNodeName = Get-DefaultNodeName
}

$env:OKX_NODE_NAME = $resolvedNodeName
$env:NODE_NAME = $resolvedNodeName

$resolvedRunMode = Normalize-RunMode $RunMode
if (-not $resolvedRunMode) {
    $resolvedRunMode = Normalize-RunMode $env:OKX_RUN_MODE
}
if (-not $resolvedRunMode) {
    $resolvedRunMode = Normalize-RunMode $env:RUN_MODE
}
if (-not $resolvedRunMode) {
    $resolvedRunMode = 'auto'
}

$env:OKX_RUN_MODE = $resolvedRunMode
$strategyVersion = if ($env:OKX_STRATEGY_VERSION) { $env:OKX_STRATEGY_VERSION } else { 'v13' }

$journalPath = Join-Path $RootDir ("journal_{0}.json" -f $resolvedNodeName)
$tradePath = Join-Path $RootDir ("active_trades_{0}.json" -f $resolvedNodeName)
$legacyJournalPath = Join-Path $RootDir 'trade_journal.json'
$legacyTradePath = Join-Path $RootDir 'active_trades.json'
$accountDumpPath = Join-Path $RootDir 'api_dump.json'
$accountOutputPath = Join-Path $RootDir 'api_output.json'
$optimizerPath = Join-Path $RootDir 'global_optimizer.json'
$cycleStatePath = Join-Path $RootDir 'optimization_cycle_state.json'
$zeroStartStatePath = Join-Path $RootDir ("zero_start_state_{0}.json" -f $resolvedNodeName)
$backupRoot = Join-Path $RootDir 'backups'
$backupDir = Join-Path $backupRoot ("zero-start-{0}" -f (Get-Date -Format 'yyyyMMdd-HHmmss'))

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

function Backup-And-Reset {
    param([string]$Path)
    if (Test-Path -LiteralPath $Path) {
        $target = Join-Path $backupDir (Split-Path -Leaf $Path)
        Move-Item -LiteralPath $Path -Destination $target -Force
    }
}

Backup-And-Reset -Path $journalPath
Backup-And-Reset -Path $tradePath
Backup-And-Reset -Path $legacyJournalPath
Backup-And-Reset -Path $legacyTradePath
Backup-And-Reset -Path $accountDumpPath
Backup-And-Reset -Path $accountOutputPath
Backup-And-Reset -Path $optimizerPath
Backup-And-Reset -Path $cycleStatePath
Backup-And-Reset -Path $zeroStartStatePath

Set-Content -LiteralPath $journalPath -Value '[]' -Encoding UTF8
Set-Content -LiteralPath $tradePath -Value '[]' -Encoding UTF8
Set-Content -LiteralPath $optimizerPath -Value '{}' -Encoding UTF8

$manifestPayload = [ordered]@{
    node_name = $resolvedNodeName
    strategy_version = $strategyVersion
    zero_start_mode = $true
    bootstrapped_at = (Get-Date).ToUniversalTime().ToString("o")
    reset_at = (Get-Date).ToUniversalTime().ToString("o")
    reset_reason = 'manual zero-start bootstrap'
}
$manifestPayload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $zeroStartStatePath -Encoding UTF8

$cyclePayload = [ordered]@{
    generation = $strategyVersion
    last_evaluated_trade_count = 0
    completed_cycles = 0
    consecutive_positive_cycles = 0
    last_checked_at = $null
    mode = 'training_active'
    summary = @{}
    top_drags = @()
    strategies = @{}
    notes = ''
}
$cyclePayload | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $cycleStatePath -Encoding UTF8

Write-Host "[OK] Zero-start initialized for node: $resolvedNodeName"
Write-Host "[OK] Run mode: $resolvedRunMode"
Write-Host "[OK] Journal: $journalPath"
Write-Host "[OK] Active trades: $tradePath"
Write-Host "[OK] Backups: $backupDir"

if (-not $SkipLaunch) {
    $env:OKX_ZERO_START_READY = '1'
    & (Join-Path $RootDir 'run_bot.bat') $resolvedRunMode
}
