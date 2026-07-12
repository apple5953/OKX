param(
    [string]$ProfileName = 'okx-demo',
    [switch]$DemoMode = $true
)

$ErrorActionPreference = 'Stop'

$RootDir = Split-Path -Parent $PSScriptRoot
$StateDir = Join-Path $RootDir 'state'
$SnapshotPath = Join-Path $StateDir 'okx_live_snapshot.json'

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null

function Convert-OkxJson {
    param([string]$Text)

    $cleanText = ($Text -replace "^\uFEFF", '')
    $startIndex = $cleanText.IndexOf('[')
    if ($startIndex -lt 0) {
        throw 'OKX CLI output did not contain JSON payload.'
    }
    $jsonText = $cleanText.Substring($startIndex)
    return ($jsonText | ConvertFrom-Json)
}

function Invoke-OkxCli {
    param([string[]]$Args)

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
    $callArgs += $Args

    $quotedArgs = $callArgs | ForEach-Object {
        if ($_ -match '\s') {
            "'" + ($_ -replace "'", "''") + "'"
        } else {
            $_
        }
    }
    $commandText = "& '$cliPath' $($quotedArgs -join ' ')"
    $output = & powershell -NoProfile -Command $commandText 2>$null
    return [string]$output
}

$positions = Convert-OkxJson (Invoke-OkxCli @('swap', 'positions', '--json'))
$balance = Convert-OkxJson (Invoke-OkxCli @('account', 'balance', '--json'))

$snapshot = [ordered]@{
    source = 'okx_cli_demo'
    synced_at = (Get-Date).ToString('s')
    account = $balance[0]
    positions = $positions
}

$snapshot | ConvertTo-Json -Depth 40 | Set-Content -LiteralPath $SnapshotPath -Encoding UTF8

$usdtDetail = $balance[0].details | Where-Object { $_.ccy -eq 'USDT' } | Select-Object -First 1
Write-Host "[OK] Wrote live snapshot to $SnapshotPath"
Write-Host ("[OK] positions={0} usdtEq={1} usdtAvail={2}" -f $positions.Count, $usdtDetail.eq, $usdtDetail.availEq)
