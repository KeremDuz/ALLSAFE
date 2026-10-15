param(
    [Parameter(Mandatory)][string]$Server,
    [switch]$AllowLoopbackHttp,
    [ValidateSet('win-x64', 'win-arm64')][string]$Runtime = 'win-x64'
)
# Run explicitly in an administrator PowerShell after publishing the package.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'agent-package.ps1')
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Yonetici PowerShell gerekli.' }
$projectRoot = Split-Path -Parent $PSScriptRoot
$packageRoot = Join-Path $projectRoot ".local/agent-publish/$Runtime"
$manifest = Test-AgentPackage -Directory $packageRoot -Runtime $Runtime
if (Get-Service -Name 'ALLSAFEAgent' -ErrorAction SilentlyContinue) { throw 'Servis zaten kayitli. Mevcut kimligi koruyarak guncelleme plani uygulayin.' }
$nativeArchitecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
if (($Runtime -eq 'win-x64' -and $nativeArchitecture -ne 'x64') -or ($Runtime -eq 'win-arm64' -and $nativeArchitecture -ne 'arm64')) {
    throw 'Paket mimarisi Windows mimarisiyle ayni olmali.'
}
$installationParent = [IO.Path]::GetFullPath((Join-Path $env:ProgramFiles 'ALLSAFE'))
$installationRoot = Join-Path $installationParent 'Agent'
$stateParent = [IO.Path]::GetFullPath((Join-Path $env:ProgramData 'ALLSAFE'))
$stateRoot = Join-Path $stateParent 'Agent'
Assert-AgentSafePath -Path $installationRoot
Assert-AgentSafePath -Path (Join-Path $stateRoot 'credential.bin')

function Set-AgentProtectedAcl {
    param([Parameter(Mandatory)][string]$Path, [Security.Principal.IdentityReference]$ServiceIdentity)
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Kurulum dizininde junction veya symbolic link kabul edilmez.' }
    if ($item.PSIsContainer) {
        $acl = New-Object Security.AccessControl.DirectorySecurity
        $inheritance = [Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit'
    } else {
        $acl = New-Object Security.AccessControl.FileSecurity
        $inheritance = [Security.AccessControl.InheritanceFlags]::None
    }
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    foreach ($sid in @('S-1-5-18', 'S-1-5-32-544')) {
        $identity = New-Object Security.Principal.SecurityIdentifier($sid)
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', $inheritance, 'None', 'Allow')))
    }
    if ($null -ne $ServiceIdentity) {
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($ServiceIdentity, 'ReadAndExecute', $inheritance, 'None', 'Allow')))
    }
    Set-Acl -LiteralPath $Path -AclObject $acl
}

# Lock each parent before creating descendants. Existing files get their own
# protected ACL; changing only the parent would retain explicit writable ACEs.
New-Item -ItemType Directory -Path $installationParent -Force | Out-Null
Set-AgentProtectedAcl -Path $installationParent
New-Item -ItemType Directory -Path $installationRoot -Force | Out-Null
Set-AgentProtectedAcl -Path $installationRoot
$relativeRoot = $installationRoot.TrimEnd('\') + '\'
$expectedFiles = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
foreach ($file in $manifest.files) { $null = $expectedFiles.Add([string]$file.path) }
$existingFiles = @(Get-AgentPackageFiles -Directory $installationRoot)
foreach ($existing in $existingFiles) {
    $relative = $existing.FullName.Substring($relativeRoot.Length).Replace('\', '/')
    if ($relative -ne 'agent-package.json' -and -not $expectedFiles.Contains($relative)) {
        throw 'Kurulum dizininde onceki pakete ait ek dosya var. Otomatik silinmedi; kontrollu guncelleme gerekli.'
    }
}
$directories = New-Object 'System.Collections.Generic.Queue[string]'
$directories.Enqueue($installationRoot)
while ($directories.Count -gt 0) {
    foreach ($entry in Get-ChildItem -LiteralPath $directories.Dequeue() -Force) {
        Set-AgentProtectedAcl -Path $entry.FullName
        if ($entry.PSIsContainer) { $directories.Enqueue($entry.FullName) }
    }
}
# Preserve relative resource directories, not just the publish root's files.
foreach ($file in @(Get-AgentPackageFiles -Directory $packageRoot)) {
    $relative = $file.FullName.Substring($packageRoot.TrimEnd('\').Length + 1)
    $destination = Join-Path $installationRoot $relative
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    Set-AgentProtectedAcl -Path $destination
}
$null = Test-AgentPackage -Directory $installationRoot -Runtime $Runtime
$agentExecutable = Join-Path $installationRoot 'Allsafe.Agent.exe'
$binaryPath = '"' + $agentExecutable + '" run' + $(if ($AllowLoopbackHttp) { ' --allow-loopback-http' } else { '' })
$createdService = $false
try {
    # Demand-start until enrollment succeeds: a reboot after partial installation
    # must not start an agent whose protected identity has not been prepared.
    & sc.exe create ALLSAFEAgent binPath= $binaryPath start= demand obj= 'NT SERVICE\ALLSAFEAgent' DisplayName= 'ALLSAFE Device Agent'
    if ($LASTEXITCODE -ne 0) { throw 'Servis olusturulamadi; baslatilmadi.' }
    $createdService = $true
    & sc.exe description ALLSAFEAgent 'ALLSAFE Windows device inventory and connection monitoring'
    if ($LASTEXITCODE -ne 0) { throw 'Servis aciklamasi ayarlanamadi.' }
    $serviceIdentity = New-Object Security.Principal.NTAccount('NT SERVICE', 'ALLSAFEAgent')
    Set-AgentProtectedAcl -Path $installationParent -ServiceIdentity $serviceIdentity
    Set-AgentProtectedAcl -Path $installationRoot -ServiceIdentity $serviceIdentity
    foreach ($entry in Get-ChildItem -LiteralPath $installationRoot -Force -Recurse) {
        Set-AgentProtectedAcl -Path $entry.FullName -ServiceIdentity $serviceIdentity
    }
    New-Item -ItemType Directory -Path $stateParent -Force | Out-Null
    Set-AgentProtectedAcl -Path $stateParent -ServiceIdentity $serviceIdentity
    # The running virtual account cannot register its own Event Log source.
    if ([Diagnostics.EventLog]::SourceExists('ALLSAFEAgent')) {
        if ([Diagnostics.EventLog]::LogNameFromSourceName('ALLSAFEAgent', '.') -ne 'Application') { throw 'ALLSAFEAgent Event Log kaynagi baska bir gunluge ait.' }
    } else { [Diagnostics.EventLog]::CreateEventSource('ALLSAFEAgent', 'Application') }
    $existingIdentity = Test-Path -LiteralPath (Join-Path $stateRoot 'credential.bin')
    if ($existingIdentity) {
        $identityArguments = @('status', '--server', $Server)
    } else { $identityArguments = @('enroll', '--server', $Server) }
    if ($AllowLoopbackHttp) { $identityArguments += '--allow-loopback-http' }
    & $agentExecutable @identityArguments
    if ($LASTEXITCODE -ne 0) { throw 'Kimlik hazirlanamadi. Yeni davet almadan once panelde cihaz kaydini kontrol edin.' }
    if ($existingIdentity) {
        $heartbeatArguments = @('once')
        if ($AllowLoopbackHttp) { $heartbeatArguments += '--allow-loopback-http' }
        & $agentExecutable @heartbeatArguments
        if ($LASTEXITCODE -ne 0) { throw 'Kayitli cihazin sunucu erisimi dogrulanamadi. Kimlik korunuyor; paneli ve ag baglantisini kontrol edin.' }
    }
    & sc.exe config ALLSAFEAgent start= delayed-auto
    if ($LASTEXITCODE -ne 0) { throw 'Servis baslangic ayari uygulanamadi.' }
    $service = Get-Service -Name ALLSAFEAgent
    try {
        $service.Start()
        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Running, [TimeSpan]::FromSeconds(20))
        Start-Sleep -Seconds 2
        $service.Refresh()
        if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Running) { throw 'Servis baslangictan hemen sonra durdu. Application gunlugunu kontrol edin.' }
    } finally { $service.Dispose() }
} catch {
    $installationError = $_
    if ($createdService) {
        try {
            $service = Get-Service -Name ALLSAFEAgent -ErrorAction SilentlyContinue
            if ($null -ne $service) {
                try {
                    if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Stopped) {
                        $service.Stop()
                        $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(20))
                    }
                } finally { $service.Dispose() }
            }
            & sc.exe delete ALLSAFEAgent
            if ($LASTEXITCODE -ne 0) { throw 'Servis kaydi temizlenemedi.' }
        } catch {
            Write-Warning 'Basarisiz kurulumun servis kaydi kaldirilamadi. Kimlik ve program dosyalari korundu; servisi elle kontrol edin.'
        }
    }
    throw $installationError
}
Write-Output 'ALLSAFEAgent calisiyor. Panelde son baglanti bilgisini kontrol edin; servis durumu sunucu baglantisini kanitlamaz.'
