$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Yonetici PowerShell gerekli.' }
$service = Get-Service -Name ALLSAFEAgent -ErrorAction SilentlyContinue
if ($service) {
    try {
        if ($service.Status -ne [ServiceProcess.ServiceControllerStatus]::Stopped) {
            $service.Stop()
            $service.WaitForStatus([ServiceProcess.ServiceControllerStatus]::Stopped, [TimeSpan]::FromSeconds(20))
        }
    } finally { $service.Dispose() }
    & sc.exe delete ALLSAFEAgent
    if ($LASTEXITCODE -ne 0) { throw 'Servis kaldirilamadi.' }
}
Write-Output 'Servis kaldirildi. Korunan cihaz kimligi ve program dosyalari yeniden kurulum icin saklandi. Erisimi panelden iptal edin.'
