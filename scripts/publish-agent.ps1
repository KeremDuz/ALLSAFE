param([ValidateSet('win-x64', 'win-arm64')][string]$Runtime = 'win-x64')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$dotnetExecutable = Get-Command dotnet -ErrorAction SilentlyContinue
if ($dotnetExecutable) { $dotnetExecutable = $dotnetExecutable.Source }
elseif (Test-Path -LiteralPath '.local/dotnet/dotnet.exe') { $dotnetExecutable = Join-Path $projectRoot '.local/dotnet/dotnet.exe' }
else { throw '.NET 10 SDK gerekli.' }
$env:DOTNET_CLI_HOME = Join-Path $projectRoot '.local/dotnet-home'
$env:NUGET_PACKAGES = Join-Path $projectRoot '.local/nuget'
$publishDirectory = Join-Path $projectRoot ".local/agent-publish/$Runtime"
& $dotnetExecutable publish apps/agent/Allsafe.Agent/Allsafe.Agent.csproj --configuration Release --runtime $Runtime --self-contained true --output $publishDirectory -p:RestoreLockedMode=true
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output "Agent paketi: $publishDirectory"
