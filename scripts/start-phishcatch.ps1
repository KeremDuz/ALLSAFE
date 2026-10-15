$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendPython = Join-Path $projectRoot '.local/phish-backend-venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $backendPython)) { throw 'Once setup-phishcatch.ps1 calistirin.' }
Set-Location -LiteralPath (Join-Path $projectRoot 'packages/phishcatch/apps/backend')
& $backendPython -m uvicorn app.main:app --host 127.0.0.1 --port 9000
exit $LASTEXITCODE
