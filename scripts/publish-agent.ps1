param([ValidateSet('win-x64', 'win-arm64')][string]$Runtime = 'win-x64')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'agent-package.ps1')
Set-Location -LiteralPath $projectRoot
$dotnetExecutable = Get-Command dotnet -ErrorAction SilentlyContinue
if ($dotnetExecutable) { $dotnetExecutable = $dotnetExecutable.Source }
elseif (Test-Path -LiteralPath '.local/dotnet/dotnet.exe') { $dotnetExecutable = Join-Path $projectRoot '.local/dotnet/dotnet.exe' }
else { throw '.NET 10 SDK gerekli.' }
$env:DOTNET_CLI_HOME = Join-Path $projectRoot '.local/dotnet-home'
$env:NUGET_PACKAGES = Join-Path $projectRoot '.local/nuget'
$publishRoot = Join-Path $projectRoot '.local/agent-publish'
$publishDirectory = Join-Path $publishRoot $Runtime
$stagingDirectory = Join-Path $publishRoot ('.stage-' + $Runtime + '-' + [Guid]::NewGuid().ToString('N'))
$previousDirectory = Join-Path $publishRoot ('.previous-' + $Runtime + '-' + [Guid]::NewGuid().ToString('N'))
Assert-AgentSafePath -Path $publishDirectory
Assert-AgentSafePath -Path $stagingDirectory
$published = $false
try {
    & $dotnetExecutable publish apps/agent/Allsafe.Agent/Allsafe.Agent.csproj --configuration Release --runtime $Runtime --self-contained true --output $stagingDirectory -p:RestoreLockedMode=true
    if ($LASTEXITCODE -ne 0) { throw 'Agent derlenemedi. Onceki paket korundu.' }
    New-AgentPackageManifest -Directory $stagingDirectory -Runtime $Runtime
    $null = Test-AgentPackage -Directory $stagingDirectory -Runtime $Runtime
    if (Test-Path -LiteralPath $publishDirectory) {
        $null = @(Get-AgentPackageFiles -Directory $publishDirectory)
        [IO.Directory]::Move($publishDirectory, $previousDirectory)
    }
    try { [IO.Directory]::Move($stagingDirectory, $publishDirectory) }
    catch {
        if ((Test-Path -LiteralPath $previousDirectory) -and -not (Test-Path -LiteralPath $publishDirectory)) {
            [IO.Directory]::Move($previousDirectory, $publishDirectory)
        }
        throw
    }
    $published = $true
} finally {
    Remove-AgentPackageDirectory -Directory $stagingDirectory -AllowedRoot $publishRoot
    if ($published) { Remove-AgentPackageDirectory -Directory $previousDirectory -AllowedRoot $publishRoot }
}
Write-Output "Agent paketi: $publishDirectory"
