[CmdletBinding()]
param([switch]$Start)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        py -3.13 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.13 and the Windows py launcher first.' }
    }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\uv.exe')) {
        .\.venv\Scripts\python.exe -m pip install 'uv==0.13.5'
        if ($LASTEXITCODE -ne 0) { throw 'uv installation failed.' }
    }
    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
    }
    .\.venv\Scripts\uv.exe sync --locked
    if ($LASTEXITCODE -ne 0) { throw 'Dependency sync failed.' }
    if ($Start) {
        docker compose config --quiet
        if ($LASTEXITCODE -ne 0) { throw 'Compose configuration failed.' }
        docker compose up --build --detach --wait
        if ($LASTEXITCODE -ne 0) { throw 'Compose startup failed. Inspect docker compose logs.' }
        $ApiAddress = docker compose port api 8000
        if ($LASTEXITCODE -ne 0) { throw 'Unable to determine the published API address.' }
        .\.venv\Scripts\uv.exe run --locked python scripts/api_smoke.py --url "http://$($ApiAddress.Trim())"
        if ($LASTEXITCODE -ne 0) { throw 'API smoke check failed.' }
    }
} finally { Pop-Location }
