[CmdletBinding()]
param([switch]$Integration)
$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $ProjectRoot
try {
    $TestTempRoot = Join-Path $ProjectRoot 'artifacts\pytest'
    New-Item -ItemType Directory -Path $TestTempRoot -Force | Out-Null
    $UnitTempPath = Join-Path $TestTempRoot ('unit-' + [Guid]::NewGuid().ToString('N'))
    .\.venv\Scripts\uv.exe run --locked ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Lint failed.' }
    .\.venv\Scripts\uv.exe run --locked ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Formatting failed.' }
    .\.venv\Scripts\uv.exe run --locked mypy
    if ($LASTEXITCODE -ne 0) { throw 'Types failed.' }
    .\.venv\Scripts\uv.exe run --locked pytest -m 'not integration' --basetemp $UnitTempPath
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed.' }
    if ($Integration) {
        $IntegrationTempPath = Join-Path $TestTempRoot ('integration-' + [Guid]::NewGuid().ToString('N'))
        .\.venv\Scripts\uv.exe run --locked pytest -m integration --basetemp $IntegrationTempPath
        if ($LASTEXITCODE -ne 0) { throw 'Integration tests failed.' }
    }
} finally { Pop-Location }
