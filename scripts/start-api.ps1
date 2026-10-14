$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    throw 'Once .\scripts\setup.ps1 calistirin.'
}
& .\.venv\Scripts\python.exe -m uvicorn allsafe_api.main:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE
