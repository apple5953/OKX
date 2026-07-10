param(
    [string]$NodeName,
    [string]$RunMode
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

$resolvedNodeName = Normalize-NodeName $NodeName
if (-not $resolvedNodeName) {
    $resolvedNodeName = Normalize-NodeName $env:OKX_NODE_NAME
}
if (-not $resolvedNodeName) {
    $resolvedNodeName = Normalize-NodeName $env:NODE_NAME
}
if (-not $resolvedNodeName) {
    $resolvedNodeName = 'node'
}

# Run auth wizard, redirecting stderr to Host to keep stdout clean for JSON parsing
Write-Host "[*] Checking license and login status..."
$wizardPath = Join-Path $RootDir "scripts\auth_wizard.py"

# Call python and catch output
$authOutput = python $wizardPath $resolvedNodeName

if ($LASTEXITCODE -ne 0) {
    Write-Error "Auth validation failed. Please check backend server."
    exit 1
}

# Convert clean JSON stdout
$authJson = $authOutput | ConvertFrom-Json
$resolvedRunMode = $authJson.mode

if (-not $resolvedRunMode) {
    $resolvedRunMode = 'demo'
}

$env:OKX_NODE_NAME = $resolvedNodeName
$env:NODE_NAME = $resolvedNodeName
$env:OKX_RUN_MODE = $resolvedRunMode

$journalPath = Join-Path $RootDir ("journal_{0}.json" -f $resolvedNodeName)
$tradePath = Join-Path $RootDir ("active_trades_{0}.json" -f $resolvedNodeName)

Write-Host "[OK] Node Name: $resolvedNodeName"
Write-Host "[OK] Run Mode: $resolvedRunMode"

& (Join-Path $RootDir 'run_bot.bat') $resolvedRunMode


