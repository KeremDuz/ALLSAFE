# Read-only local checks. Does not install services, open ports, read key contents or connect remotely.
[CmdletBinding()]
param(
    [ValidateRange(1, 65535)]
    [int]$SshPort = 22
)

$ErrorActionPreference = 'Stop'

function Read-RegistrySetting {
    param([string]$Path, [string]$Name)
    try {
        $item = Get-ItemProperty -LiteralPath $Path -Name $Name -ErrorAction Stop
        return [ordered]@{ status = 'observed'; value = $item.$Name }
    } catch [System.Management.Automation.ItemNotFoundException] {
        return [ordered]@{ status = 'not_configured'; value = $null }
    } catch [System.Management.Automation.PSArgumentException] {
        return [ordered]@{ status = 'not_configured'; value = $null }
    } catch {
        return [ordered]@{ status = 'unknown'; value = $null }
    }
}

function Read-ServiceState {
    param([string]$Name)
    try {
        $service = Get-Service -Name $Name -ErrorAction Stop
        try {
            return [ordered]@{
                status = 'observed'
                present = $true
                state = $service.Status.ToString()
                start_type = $service.StartType.ToString()
            }
        } finally {
            $service.Dispose()
        }
    } catch {
        if ($_.FullyQualifiedErrorId -like 'NoServiceFoundForGivenName*') {
            return [ordered]@{ status = 'not_observed'; present = $null; state = $null; start_type = $null }
        }
        return [ordered]@{ status = 'unknown'; present = $null; state = $null; start_type = $null }
    }
}

function Read-ListenerState {
    param([int]$Port)
    try {
        # A listener alone does not prove which service owns it or that remote routing works.
        $listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
        return [ordered]@{ status = 'observed'; port = $Port; listening = @($listeners | Where-Object LocalPort -eq $Port).Count -gt 0 }
    } catch {
        return [ordered]@{ status = 'unknown'; port = $Port; listening = $null }
    }
}

function Read-FirewallRules {
    param([string[]]$Names)
    $observedRules = @()
    foreach ($name in $Names) {
        try {
            $rules = @(Get-NetFirewallRule -PolicyStore ActiveStore -Name $name -ErrorAction Stop)
            foreach ($rule in $rules) {
                $scope = 'unknown'
                try {
                    $addresses = @($rule | Get-NetFirewallAddressFilter -ErrorAction Stop)
                    $remoteAddresses = @($addresses | ForEach-Object { $_.RemoteAddress })
                    if ($remoteAddresses -contains 'Any') { $scope = 'any' }
                    elseif ($remoteAddresses.Count -gt 0) { $scope = 'restricted' }
                } catch { }
                $observedRules += [ordered]@{
                    name = $rule.Name
                    enabled = $rule.Enabled.ToString()
                    direction = $rule.Direction.ToString()
                    action = $rule.Action.ToString()
                    profile = $rule.Profile.ToString()
                    remote_address_scope = $scope
                }
            }
        } catch {
            # Do not claim that a missing default rule means the port is blocked: custom rules may exist.
            $observedRules += [ordered]@{ name = $name; status = 'not_observed_or_unavailable' }
        }
    }
    return ,$observedRules
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    [ordered]@{ schema_version = 1; read_only = $true; status = 'unsupported_platform' } | ConvertTo-Json
    return
}

$elevated = $null
try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    try {
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        $elevated = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    } finally {
        $identity.Dispose()
    }
} catch { }

$edition = Read-RegistrySetting -Path 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion' -Name 'EditionID'
$rdpHostSupport = 'unknown'
if ($edition.status -eq 'observed') {
    if ($edition.value -match '^(Core|Starter)') { $rdpHostSupport = 'not_supported' }
    elseif ($edition.value -match '^(Professional|Enterprise|Education|Server|IoTEnterprise)') { $rdpHostSupport = 'supported_edition' }
}

$capability = [ordered]@{ status = 'unknown'; state = $null }
try {
    $serverCapability = @(Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction Stop)
    if ($serverCapability.Count -eq 1) {
        $capability = [ordered]@{ status = 'observed'; state = $serverCapability[0].State.ToString() }
    }
} catch { }

$defaultShell = Read-RegistrySetting -Path 'HKLM:\SOFTWARE\OpenSSH' -Name 'DefaultShell'
if ($defaultShell.status -eq 'not_configured') {
    $defaultShell = [ordered]@{ status = 'default'; value = 'cmd.exe' }
}

$rdpKey = 'HKLM:\SYSTEM\CurrentControlSet\Control\Terminal Server'
$rdpTcpKey = Join-Path $rdpKey 'WinStations\RDP-Tcp'
$rdpPolicyKey = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows NT\Terminal Services'
$rdpPortSetting = Read-RegistrySetting -Path $rdpTcpKey -Name 'PortNumber'
$rdpListener = [ordered]@{ status = 'unknown'; port = $null; listening = $null }
if ($rdpPortSetting.status -eq 'observed' -and [int64]$rdpPortSetting.value -ge 1 -and [int64]$rdpPortSetting.value -le 65535) {
    $rdpListener = Read-ListenerState -Port ([int]$rdpPortSetting.value)
}

$report = [ordered]@{
    schema_version = 1
    checked_at_utc = [DateTime]::UtcNow.ToString('o')
    read_only = $true
    elevated = $elevated
    windows = [ordered]@{ edition_id = $edition; rdp_host_support = $rdpHostSupport }
    ssh = [ordered]@{
        capability = $capability
        service = Read-ServiceState -Name 'sshd'
        default_shell = $defaultShell
        listener = Read-ListenerState -Port $SshPort
        default_firewall_rules = Read-FirewallRules -Names @('OpenSSH-Server-In-TCP')
    }
    rdp = [ordered]@{
        service = Read-ServiceState -Name 'TermService'
        deny_connections_local = Read-RegistrySetting -Path $rdpKey -Name 'fDenyTSConnections'
        deny_connections_policy = Read-RegistrySetting -Path $rdpPolicyKey -Name 'fDenyTSConnections'
        require_nla_local = Read-RegistrySetting -Path $rdpTcpKey -Name 'UserAuthentication'
        require_nla_policy = Read-RegistrySetting -Path $rdpPolicyKey -Name 'UserAuthentication'
        listener = $rdpListener
        default_firewall_rules = Read-FirewallRules -Names @('RemoteDesktop-UserMode-In-TCP', 'RemoteDesktop-UserMode-In-UDP')
    }
    connection_verified = $false
    note = 'Local observations only. Unknown checks are not failures or proof of readiness. Authentication, host trust, effective policy and remote network reachability require separate acceptance.'
}
$report | ConvertTo-Json -Depth 8
