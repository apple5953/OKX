param(
    [string]$RunMode
)

$ErrorActionPreference = 'Stop'

function Normalize-RunMode {
    param([string]$Value)
    if ($null -eq $Value) {
        return ''
    }
    $text = $Value.Trim().ToLowerInvariant()
    switch ($text) {
        'auto' { return 'auto' }
        'mock' { return 'mock' }
        'live' { return 'live' }
        'simulation' { return 'mock' }
        'sim' { return 'mock' }
        'paper' { return 'mock' }
        'demo' { return 'mock' }
        default { return '' }
    }
}

$resolved = Normalize-RunMode $RunMode
if (-not $resolved) {
    $resolved = Normalize-RunMode $env:OKX_RUN_MODE
}
if (-not $resolved) {
    $choice = Read-Host 'Enter run mode (auto / mock / live)'
    $resolved = Normalize-RunMode $choice
}

if (-not $resolved) {
    throw "Run mode must be one of: auto, mock, live."
}

[Environment]::SetEnvironmentVariable('OKX_RUN_MODE', $resolved, 'User')
$env:OKX_RUN_MODE = $resolved

Write-Host "[OK] OKX_RUN_MODE set to: $resolved"
