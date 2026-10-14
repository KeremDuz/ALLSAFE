param([Parameter(Mandatory)][string]$Server, [switch]$AllowLoopbackHttp)
# Run explicitly in an administrator PowerShell after publishing win-x64.
$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Yonetici PowerShell gerekli.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
$packageRoot = Join-Path $projectRoot '.local/agent-publish/win-x64'
if (-not (Test-Path -LiteralPath (Join-Path $packageRoot 'Allsafe.Agent.exe'))) { throw 'Once publish-agent.ps1 calistirin.' }
if (Get-Service -Name 'ALLSAFEAgent' -ErrorAction SilentlyContinue) { throw 'Servis zaten kayitli. Mevcut kimligi koruyarak guncelleme plani uygulayin.' }
$installationRoot = [IO.Path]::GetFullPath((Join-Path $env:ProgramFiles 'ALLSAFE/Agent'))
$expectedParent = [IO.Path]::GetFullPath($env:ProgramFiles).TrimEnd('\') + '\'
if (-not $installationRoot.StartsWith($expectedParent, [StringComparison]::OrdinalIgnoreCase)) { throw 'Kurulum dizini dogrulanamadi.' }
New-Item -ItemType Directory -Path $installationRoot -Force | Out-Null
$directoryAcl = New-Object Security.AccessControl.DirectorySecurity
$directoryAcl.SetAccessRuleProtection($true, $false)
foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
    $identity = New-Object Security.Principal.SecurityIdentifier($sid)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $directoryAcl.AddAccessRule($rule)
}
Set-Acl -LiteralPath $installationRoot -AclObject $directoryAcl
Get-ChildItem -LiteralPath $packageRoot -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $installationRoot }
$agentExecutable = Join-Path $installationRoot 'Allsafe.Agent.exe'
$binaryPath = '"' + $agentExecutable + '" run' + $(if ($AllowLoopbackHttp) { ' --allow-loopback-http' } else { '' })
& sc.exe create ALLSAFEAgent binPath= $binaryPath start= auto obj= 'NT SERVICE\ALLSAFEAgent' DisplayName= 'ALLSAFE Device Agent'
if ($LASTEXITCODE -ne 0) { throw 'Servis olusturulamadi; baslatilmadi.' }
$serviceIdentity = New-Object Security.Principal.NTAccount('NT SERVICE', 'ALLSAFEAgent')
$serviceRule = New-Object Security.AccessControl.FileSystemAccessRule($serviceIdentity, 'ReadAndExecute', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
$directoryAcl.AddAccessRule($serviceRule)
Set-Acl -LiteralPath $installationRoot -AclObject $directoryAcl
$stateRoot = Join-Path $env:ProgramData 'ALLSAFE/Agent'
$stateParent = Join-Path $env:ProgramData 'ALLSAFE'
if ((Test-Path -LiteralPath $stateParent) -and ((Get-Item -LiteralPath $stateParent).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Kimlik ust dizininde reparse point kabul edilmez.' }
New-Item -ItemType Directory -Path $stateParent -Force | Out-Null
$stateParentAcl = New-Object Security.AccessControl.DirectorySecurity
$stateParentAcl.SetAccessRuleProtection($true, $false)
$administratorsIdentity = New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')
$stateParentAcl.SetOwner($administratorsIdentity)
foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
    $identity = New-Object Security.Principal.SecurityIdentifier($sid)
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow')
    $stateParentAcl.AddAccessRule($rule)
}
$stateParentAcl.AddAccessRule($serviceRule)
Set-Acl -LiteralPath $stateParent -AclObject $stateParentAcl
if (Test-Path -LiteralPath (Join-Path $stateRoot 'credential.bin')) {
    $statusArguments = @('status', '--server', $Server)
    if ($AllowLoopbackHttp) { $statusArguments += '--allow-loopback-http' }
    & $agentExecutable @statusArguments
} else {
    $enrollmentArguments = @('enroll', '--server', $Server)
    if ($AllowLoopbackHttp) { $enrollmentArguments += '--allow-loopback-http' }
    & $agentExecutable @enrollmentArguments
}
if ($LASTEXITCODE -ne 0) { throw 'Kimlik hazirlanamadi. Servis kayitli fakat baslatilmadi. Yeni davet almadan once paneli kontrol edin.' }
Start-Service -Name ALLSAFEAgent
Write-Output 'ALLSAFEAgent baslatildi. Panelde cihaz ve son baglanti bilgisini kontrol edin.'
