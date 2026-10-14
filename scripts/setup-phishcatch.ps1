param([switch]$IncludeTests)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$backendDirectory = Join-Path $projectRoot 'packages/phishcatch/apps/backend'
if (-not (Test-Path -LiteralPath (Join-Path $backendDirectory 'requirements.lock'))) { throw 'Once PhishCatch submodule surumunu guncelleyin: git submodule update --init --recursive.' }
$corePython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $corePython)) { throw 'Once scripts/setup.ps1 calistirin.' }
$backendPython = Join-Path $projectRoot '.local/phish-backend-venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $backendPython)) {
    & $corePython -m venv .local/phish-backend-venv
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
$requirements = if ($IncludeTests) { 'requirements-dev.lock' } else { 'requirements.lock' }
& $backendPython -m pip install --require-hashes -r (Join-Path $backendDirectory $requirements)
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
# The key is generated/read only in process memory and written to ignored .env files.
@'
from pathlib import Path
import re
import secrets
root=Path.cwd()
core=root/'.env'
backend=root/'packages/phishcatch/apps/backend/.env'
if not core.exists():
    raise SystemExit('Core .env is missing; run setup.ps1 first.')
core_text=core.read_text(encoding='utf-8')
backend_text=backend.read_text(encoding='utf-8') if backend.exists() else ''
match=re.search(r'(?m)^ALLSAFE_PHISHCATCH_INTEGRATION_KEY=(.+)$',core_text)
key=match.group(1).strip() if match else secrets.token_urlsafe(32)
if len(key)<32:
    raise SystemExit('Configured integration key must contain at least 32 characters.')
def set_value(text,name,value):
    pattern=rf'(?m)^{re.escape(name)}=.*$'
    return re.sub(pattern,lambda _:f'{name}={value}',text) if re.search(pattern,text) else text.rstrip()+f'\n{name}={value}\n'
core_text=set_value(core_text,'ALLSAFE_PHISHCATCH_INTEGRATION_KEY',key)
core_text=set_value(core_text,'ALLSAFE_PHISHCATCH_URL','http://127.0.0.1:9000')
core_text=set_value(core_text,'ALLSAFE_PHISHCATCH_ALLOW_LOOPBACK_HTTP','true')
backend_text=set_value(backend_text,'ALLSAFE_INTEGRATION_KEY',key)
core.write_text(core_text,encoding='utf-8')
backend.write_text(backend_text,encoding='utf-8')
print('Local PhishCatch connector configured. No credentials printed.')
'@ | & $corePython -
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output 'PhishCatch hazir. API yeniden baslatilmali; ikinci terminalde start-phishcatch.ps1 calistirin.'
