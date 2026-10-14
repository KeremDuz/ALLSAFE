$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$dotnetExecutable = Get-Command dotnet -ErrorAction SilentlyContinue
if ($dotnetExecutable) { $dotnetExecutable = $dotnetExecutable.Source }
elseif (Test-Path -LiteralPath '.local/dotnet/dotnet.exe') { $dotnetExecutable = Join-Path $projectRoot '.local/dotnet/dotnet.exe' }
else { throw '.NET 10 SDK gerekli.' }
$env:DOTNET_CLI_HOME = Join-Path $projectRoot '.local/dotnet-home'
$env:NUGET_PACKAGES = Join-Path $projectRoot '.local/nuget'
& $dotnetExecutable restore apps/agent/Allsafe.Agent.Tests/Allsafe.Agent.Tests.csproj --locked-mode
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $dotnetExecutable test apps/agent/Allsafe.Agent.Tests/Allsafe.Agent.Tests.csproj --no-restore --configuration Release
exit $LASTEXITCODE
