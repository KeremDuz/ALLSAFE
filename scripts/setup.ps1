param([string]$PythonPath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot

if (-not $PythonPath) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    if (Test-Path -LiteralPath $bundledPython) {
        $PythonPath = $bundledPython
    } else {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
            $PythonPath = $pythonCommand.Source
        } else {
            throw 'Python 3.12+ bulunamadi. -PythonPath ile python.exe yolunu verin.'
        }
    }
}

& $PythonPath -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'
if ($LASTEXITCODE -ne 0) { throw 'Python 3.12+ gerekli.' }
& $PythonPath -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Python ortami olusturulamadi.' }
& .\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.lock
if ($LASTEXITCODE -ne 0) { throw 'Bagimliliklar kurulamadi.' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -e apps/api
if ($LASTEXITCODE -ne 0) { throw 'API paketi kurulamadi.' }

if (-not (Test-Path -LiteralPath '.env')) {
    $randomBytes = New-Object byte[] 32
    $randomGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $randomGenerator.GetBytes($randomBytes) } finally { $randomGenerator.Dispose() }
    $adminToken = [Convert]::ToBase64String($randomBytes)
    $template = Get-Content -LiteralPath '.env.example' -Raw
    $template.Replace('ALLSAFE_BOOTSTRAP_ADMIN_TOKEN=', "ALLSAFE_BOOTSTRAP_ADMIN_TOKEN=$adminToken") |
        Set-Content -LiteralPath '.env' -Encoding utf8
    Write-Host 'Yerel .env olusturuldu; yonetici anahtari ekrana yazilmadi.'
}
$localConfiguration = Get-Content -LiteralPath '.env' -Raw
if ($localConfiguration -notmatch '(?m)^ALLSAFE_INITIAL_ADMIN_PASSWORD=\S[^\r\n]*$') {
    $passwordBytes = New-Object byte[] 32
    $passwordGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $passwordGenerator.GetBytes($passwordBytes) } finally { $passwordGenerator.Dispose() }
    $initialPassword = [Convert]::ToBase64String($passwordBytes)
    if ($localConfiguration -match '(?m)^ALLSAFE_INITIAL_ADMIN_PASSWORD=\s*$') {
        $localConfiguration = [regex]::Replace($localConfiguration, '(?m)^ALLSAFE_INITIAL_ADMIN_PASSWORD=[^\r\n]*', "ALLSAFE_INITIAL_ADMIN_PASSWORD=$initialPassword")
    } else {
        $localConfiguration += "`nALLSAFE_INITIAL_ADMIN_PASSWORD=$initialPassword`n"
    }
    $localConfiguration | Set-Content -LiteralPath '.env' -Encoding utf8
    Write-Host 'Ilk yonetici parolasi .env icinde olusturuldu; ekrana yazilmadi.'
}
Write-Host 'Kurulum tamamlandi. API: .\scripts\start-api.ps1; yonetici: admin@allsafe.local'
