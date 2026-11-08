# Offline regression checks: no service, Event Log, Program Files or ProgramData changes.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'agent-package.ps1')
$projectRoot = Split-Path -Parent $PSScriptRoot
$testRoot = Join-Path $projectRoot ('.local/agent-package-tests-' + [Guid]::NewGuid().ToString('N'))
$testCount = 0
$fixtureCount = 0
$junctions = New-Object 'System.Collections.Generic.List[string]'
function New-PackageFixture {
    $script:fixtureCount++
    $directory = Join-Path $testRoot ('fixture-' + $script:fixtureCount)
    New-Item -ItemType Directory -Path (Join-Path $directory 'tr') -Force | Out-Null
    foreach ($file in @('Allsafe.Agent.exe', 'Allsafe.Agent.dll', 'Allsafe.Agent.deps.json', 'Allsafe.Agent.runtimeconfig.json', 'tr/resource.dll')) {
        Set-Content -LiteralPath (Join-Path $directory $file) -Value 'fixture-data' -Encoding UTF8
    }
    New-AgentPackageManifest -Directory $directory -Runtime win-x64
    return $directory
}
function Assert-Rejected {
    param([scriptblock]$Action)
    $rejected = $false
    try { & $Action | Out-Null } catch { $rejected = $true }
    if (-not $rejected) { throw 'Beklenen guvensiz paket kabul edildi.' }
    $script:testCount++
}
function Save-FixtureManifest {
    param([string]$Directory, [object]$Manifest)
    $Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Directory 'agent-package.json') -Encoding UTF8
}
try {
    foreach ($name in @('agent-package.ps1', 'publish-agent.ps1', 'install-agent.ps1', 'uninstall-agent.ps1')) {
        $parseTokens = $null
        $parseErrors = $null
        $null = [Management.Automation.Language.Parser]::ParseFile((Join-Path $PSScriptRoot $name), [ref]$parseTokens, [ref]$parseErrors)
        if ($parseErrors.Count -ne 0) { throw "PowerShell parse hatasi: $name" }
        $testCount++
    }
    $fixture = New-PackageFixture
    $manifest = Test-AgentPackage -Directory $fixture -Runtime win-x64
    if (@($manifest.files).Count -ne 5 -or @($manifest.files.path) -notcontains 'tr/resource.dll') { throw 'Paket kaynak alt dizini korunmadi.' }
    $testCount++

    $fixture = New-PackageFixture
    Set-Content -LiteralPath (Join-Path $fixture 'Allsafe.Agent.dll') -Value 'fixture-evil' -Encoding UTF8
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    $fixture = New-PackageFixture
    Remove-Item -LiteralPath (Join-Path $fixture 'Allsafe.Agent.dll')
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    $fixture = New-PackageFixture
    Set-Content -LiteralPath (Join-Path $fixture 'stale.dll') -Value 'stale'
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    $fixture = New-PackageFixture
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-arm64 }
    $manifest = Get-Content -LiteralPath (Join-Path $fixture 'agent-package.json') -Raw | ConvertFrom-Json
    $manifest.files[0].path = '../escape.dll'
    Save-FixtureManifest $fixture $manifest
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    $fixture = New-PackageFixture
    $manifest = Get-Content -LiteralPath (Join-Path $fixture 'agent-package.json') -Raw | ConvertFrom-Json
    $manifest.files += $manifest.files[0]
    Save-FixtureManifest $fixture $manifest
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    $fixture = New-PackageFixture
    $manifest = Get-Content -LiteralPath (Join-Path $fixture 'agent-package.json') -Raw | ConvertFrom-Json
    $manifest.files[0].path += '.'
    Save-FixtureManifest $fixture $manifest
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    $fixture = New-PackageFixture
    Remove-Item -LiteralPath (Join-Path $fixture 'Allsafe.Agent.exe')
    New-AgentPackageManifest -Directory $fixture -Runtime win-x64
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }

    $fixture = New-PackageFixture
    $link = Join-Path $testRoot 'parent-link'
    New-Item -ItemType Junction -Path $link -Target $fixture | Out-Null
    $junctions.Add($link)
    Assert-Rejected { Assert-AgentSafePath -Path (Join-Path $link 'missing/Agent') }
    $insideLink = Join-Path $fixture 'linked'
    New-Item -ItemType Junction -Path $insideLink -Target (Join-Path $fixture 'tr') | Out-Null
    $junctions.Add($insideLink)
    Assert-Rejected { Test-AgentPackage -Directory $fixture -Runtime win-x64 }
    Assert-Rejected { Remove-AgentPackageDirectory -Directory $testRoot -AllowedRoot $testRoot }
    Assert-Rejected { Remove-AgentPackageDirectory -Directory (Join-Path $testRoot '../other') -AllowedRoot $testRoot }
    Write-Output "$testCount offline agent package checks passed. No services or system settings changed."
} finally {
    foreach ($junction in $junctions) {
        # Delete only the checked junction itself, never recurse through its target.
        $item = Get-Item -LiteralPath $junction -Force -ErrorAction SilentlyContinue
        if ($null -ne $item) {
            $boundary = [IO.Path]::GetFullPath($testRoot).TrimEnd('\') + '\'
            if (-not $item.FullName.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase) -or
                -not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Test junction temizleme hedefi dogrulanamadi.' }
            [IO.Directory]::Delete($item.FullName, $false)
        }
    }
    Remove-AgentPackageDirectory -Directory $testRoot -AllowedRoot (Join-Path $projectRoot '.local')
}
