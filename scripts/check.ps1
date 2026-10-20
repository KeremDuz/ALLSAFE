$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$testDirectory = Join-Path '.local' ('pytest-' + [guid]::NewGuid().ToString('N'))
& .\.venv\Scripts\python.exe -m ruff check apps/api scripts/demo_enrollment.py scripts/home_server.py deploy/home/tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m ruff format --check apps/api scripts/demo_enrollment.py scripts/home_server.py deploy/home/tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m pytest apps/api/tests -q --basetemp=$testDirectory
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& .\.venv\Scripts\python.exe -m unittest discover -s deploy/home/tests -v
exit $LASTEXITCODE
