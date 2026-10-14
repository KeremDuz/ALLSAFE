$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Yonetici PowerShell gerekli.' }
$service = Get-Service -Name ALLSAFEAgent -ErrorAction SilentlyContinue
if ($service) {
    Stop-Service -Name ALLSAFEAgent
    & sc.exe delete ALLSAFEAgent
    if ($LASTEXITCODE -ne 0) { throw 'Servis kaldirilamadi.' }
}
Write-Output 'Servis kaldirildi. Korunan cihaz kimligi ve program dosyalari yeniden kurulum icin saklandi. Erisimi panelden iptal edin.'
