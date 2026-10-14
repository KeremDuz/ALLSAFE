$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot 'apps/web'
Set-Location -LiteralPath $webRoot
if (-not (Test-Path -LiteralPath 'node_modules')) {
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Panel bagimliliklari kurulamadi.' }
}
& npm run dev
exit $LASTEXITCODE
