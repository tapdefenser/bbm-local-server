param([string]$ServerUrl)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) { throw 'Run tools/setup.ps1 first' }
    if ($ServerUrl) {
        & .venv/Scripts/python.exe -m tools.prepare_local --server $ServerUrl
        if ($LASTEXITCODE -ne 0) { throw 'Configuration failed' }
    }
    if (-not (Test-Path -LiteralPath '.local/server.json')) {
        throw 'First run: ./start-server.ps1 -ServerUrl https://YOUR_PC_IP:9100'
    }
    & .venv/Scripts/python.exe -m bbm.server
} finally {
    Pop-Location
}
