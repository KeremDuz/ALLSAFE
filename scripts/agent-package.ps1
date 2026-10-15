# Shared offline package validation. This file does not install or start services.
function Assert-AgentSafePath {
    param([Parameter(Mandatory)][string]$Path)
    $current = [IO.Path]::GetFullPath($Path)
    while ($current) {
        try { $item = Get-Item -LiteralPath $current -Force -ErrorAction Stop }
        catch [System.Management.Automation.ItemNotFoundException] { $item = $null }
        if ($null -ne $item) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Agent yolunda junction veya symbolic link kabul edilmez.'
            }
        }
        $parent = [IO.Directory]::GetParent($current)
        if ($null -eq $parent) { break }
        $current = $parent.FullName
    }
}

function Get-AgentPackageFiles {
    param([Parameter(Mandatory)][string]$Directory)
    Assert-AgentSafePath -Path $Directory
    if (-not (Test-Path -LiteralPath $Directory -PathType Container)) { throw 'Agent paket dizini bulunamadi.' }
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push([IO.Path]::GetFullPath($Directory))
    while ($pending.Count -gt 0) {
        foreach ($entry in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if ($entry.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Agent paketinde junction veya symbolic link kabul edilmez.' }
            if ($entry.PSIsContainer) { $pending.Push($entry.FullName) }
            else { $entry }
        }
    }
}

function New-AgentPackageManifest {
    param([Parameter(Mandatory)][string]$Directory, [Parameter(Mandatory)][ValidateSet('win-x64', 'win-arm64')][string]$Runtime)
    $root = [IO.Path]::GetFullPath($Directory).TrimEnd('\') + '\'
    $files = @(Get-AgentPackageFiles -Directory $Directory | Where-Object { $_.FullName -ne ($root + 'agent-package.json') } | Sort-Object FullName | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($root.Length).Replace('\', '/')
            length = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    })
    [ordered]@{ schemaVersion = 1; runtime = $Runtime; files = $files } |
        ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $Directory 'agent-package.json') -Encoding UTF8
}

function Test-AgentPackage {
    param([Parameter(Mandatory)][string]$Directory, [Parameter(Mandatory)][ValidateSet('win-x64', 'win-arm64')][string]$Runtime)
    $files = @(Get-AgentPackageFiles -Directory $Directory)
    $manifestPath = Join-Path $Directory 'agent-package.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) { throw 'Paket manifesti eksik. publish-agent.ps1 ile yeniden paketleyin.' }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schemaVersion -ne 1 -or $manifest.runtime -ne $Runtime -or $null -eq $manifest.files) { throw 'Agent paket manifesti veya mimarisi gecersiz.' }
    $root = [IO.Path]::GetFullPath($Directory).TrimEnd('\') + '\'
    $expected = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
    foreach ($file in @($manifest.files)) {
        $relative = [string]$file.path
        if ([string]::IsNullOrWhiteSpace($relative) -or [IO.Path]::IsPathRooted($relative) -or
            $relative.Contains('\') -or $relative.Contains(':') -or $relative.Contains('//') -or
            $relative.EndsWith('/') -or $relative -match '(^|/)\.\.?(/|$)' -or
            $relative -match '[. ](/|$)' -or
            $relative -eq 'agent-package.json' -or -not $expected.Add($relative)) { throw 'Agent manifestinde gecersiz veya yinelenen dosya yolu.' }
        $target = [IO.Path]::GetFullPath((Join-Path $Directory $relative))
        if (-not $target.StartsWith($root, [StringComparison]::OrdinalIgnoreCase)) { throw 'Agent paket yolu dizin disina cikiyor.' }
        if (-not (Test-Path -LiteralPath $target -PathType Leaf) -or
            (Get-Item -LiteralPath $target -Force).Length -ne [long]$file.length -or
            [string]$file.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or
            (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne [string]$file.sha256) { throw 'Agent paketi eksik veya dosya butunlugu gecersiz.' }
    }
    foreach ($actual in $files) {
        $relative = $actual.FullName.Substring($root.Length).Replace('\', '/')
        if ($relative -ne 'agent-package.json' -and -not $expected.Contains($relative)) { throw 'Agent paketinde manifeste dahil olmayan dosya var.' }
    }
    foreach ($required in @('Allsafe.Agent.exe', 'Allsafe.Agent.dll', 'Allsafe.Agent.deps.json', 'Allsafe.Agent.runtimeconfig.json')) {
        if (-not $expected.Contains($required)) { throw 'Agent paketinin gerekli dosyalari eksik.' }
    }
    if ($files.Count -ne ($expected.Count + 1)) { throw 'Agent paketinde manifeste dahil olmayan dosya var.' }
    return $manifest
}

function Remove-AgentPackageDirectory {
    param([Parameter(Mandatory)][string]$Directory, [Parameter(Mandatory)][string]$AllowedRoot)
    $full = [IO.Path]::GetFullPath($Directory).TrimEnd('\')
    $boundary = [IO.Path]::GetFullPath($AllowedRoot).TrimEnd('\') + '\'
    if (-not $full.StartsWith($boundary, [StringComparison]::OrdinalIgnoreCase)) { throw 'Paket temizleme hedefi izin verilen dizinin disinda.' }
    if (Test-Path -LiteralPath $full) {
        $null = @(Get-AgentPackageFiles -Directory $full)
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}
