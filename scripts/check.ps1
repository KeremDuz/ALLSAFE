$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$testDirectory = Join-Path '.local' ('pytest-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -m ruff check apps/api scripts/demo_enrollment.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m ruff format --check apps/api scripts/demo_enrollment.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m pytest apps/api/tests -q --basetemp=$testDirectory
exit $LASTEXITCODE
