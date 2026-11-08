# Copies the newest weekly backup of the home server to this PC, so a disk failure on the server
# does not take the backups with it. Run weekly by a Windows scheduled task; see
# deploy/server/README.md. The archives contain secrets (.env files): keep the folder private.
param(
    [string]$Destination = (Join-Path $env:USERPROFILE 'ALLSAFE-Backups'),
    [string]$Server = 'keremserver@100.87.174.61',
    [string]$KeyFile = (Join-Path $env:USERPROFILE '.ssh\allsafe_server_ed25519'),
    [int]$Keep = 8
)
$ErrorActionPreference = 'Stop'
$sshOptions = @('-i', $KeyFile, '-o', 'IdentitiesOnly=yes', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20')

New-Item -ItemType Directory -Force -Path $Destination | Out-Null
$latest = "$(& ssh @sshOptions $Server 'readlink stacks/backups/weekly/allsafe-backup-latest.tar')".Trim()
if ($LASTEXITCODE -ne 0 -or $latest -notmatch '^allsafe-backup-[0-9TZ]+\.tar$') {
    throw "Sunucudaki son yedek bulunamadi: '$latest'"
}
$target = Join-Path $Destination $latest
if (-not (Test-Path -LiteralPath $target)) {
    & scp @sshOptions "${Server}:stacks/backups/weekly/$latest" "$target.part"
    if ($LASTEXITCODE -ne 0) { throw 'Yedek kopyalanamadi.' }
    Move-Item -LiteralPath "$target.part" -Destination $target
    Write-Host "Kopyalandi: $target"
} else {
    Write-Host "Zaten var: $target"
}
Get-ChildItem -LiteralPath $Destination -Filter 'allsafe-backup-*.tar' |
    Sort-Object Name -Descending | Select-Object -Skip $Keep | Remove-Item
