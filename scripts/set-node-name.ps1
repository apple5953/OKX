param(
    [Parameter(Mandatory = $true)]
    [string]$NodeName
)

$ErrorActionPreference = 'Stop'

function Normalize-NodeName {
    param([string]$Value)
    if ($null -eq $Value) {
        return ''
    }
    $text = $Value.Trim()
    $text = $text -replace '[^A-Za-z0-9._-]+', '-'
    $text = $text.Trim('.','_','-')
    return $text
}

$resolved = Normalize-NodeName $NodeName
if (-not $resolved) {
    throw "Node name cannot be empty."
}

[Environment]::SetEnvironmentVariable('OKX_NODE_NAME', $resolved, 'User')
[Environment]::SetEnvironmentVariable('NODE_NAME', $resolved, 'User')
$env:OKX_NODE_NAME = $resolved
$env:NODE_NAME = $resolved

Write-Host "[OK] OKX_NODE_NAME set to: $resolved"
Write-Host "[OK] NODE_NAME set to: $resolved"
