param(
    [string]$DevelopmentDirectory,
    [switch]$AllowLoopbackHttp,
    [switch]$Unattended,
    [string]$AgentPath
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $AgentPath) {
    $installed = Join-Path $env:ProgramFiles 'ALLSAFE/Agent/Allsafe.Agent.exe'
    $published = Join-Path $projectRoot '.local/agent-publish/win-x64/Allsafe.Agent.exe'
    if ($DevelopmentDirectory -and (Test-Path -LiteralPath $published)) { $AgentPath = $published }
    elseif (Test-Path -LiteralPath $installed) { $AgentPath = $installed }
    elseif (Test-Path -LiteralPath $published) { $AgentPath = $published }
    else { throw 'Önce ajanı yayımlayın veya -AgentPath ile mevcut ajanı belirtin.' }
}
$resolvedAgent = (Resolve-Path -LiteralPath $AgentPath).Path
$arguments = @('desktop')
if ($DevelopmentDirectory) {
    if ([System.IO.Path]::IsPathRooted($DevelopmentDirectory)) { $state = [System.IO.Path]::GetFullPath($DevelopmentDirectory) }
    else { $state = [System.IO.Path]::GetFullPath((Join-Path $projectRoot $DevelopmentDirectory)) }
    $arguments += @('--dev-state-dir', $state)
}
if ($AllowLoopbackHttp) { $arguments += '--allow-loopback-http' }
if ($Unattended) { $arguments += '--unattended' }
if ($Unattended -or -not $DevelopmentDirectory) {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try { $administrator = (New-Object Security.Principal.WindowsPrincipal($identity)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
    finally { $identity.Dispose() }
    if (-not $administrator) { throw 'Yönetilen erişim veya korunan cihaz kimliği için bu betiği açıkça Yönetici olarak başlatın. Ajanın dosya izinlerini değiştirmeyin.' }
}
# Foreground execution is deliberate: this command never installs or silently starts a companion.
& $resolvedAgent @arguments
if ($LASTEXITCODE -ne 0) { throw "Uzaktan destek uygulaması durdu (kod: $LASTEXITCODE)." }
