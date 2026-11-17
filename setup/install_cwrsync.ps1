$ErrorActionPreference = 'Stop'

$version = '6.5.0'
$archiveName = "cwrsync_${version}_x64_free.zip"
$downloadUrl = "https://itefix.net/downloads/cwrsync/$archiveName"
$expectedHash = '8dc20afec889908c05c2abaa21d37f3fcad3e7ea5f3f37e95b25e6178f6b983a'

$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$toolsDirectory = Join-Path $repository '.tools'
$installDirectory = Join-Path $toolsDirectory 'cwrsync'
$versionFile = Join-Path $installDirectory '.version'
$cacheScript = Join-Path $PSScriptRoot 'cache_cwrsync_accounts.ps1'

if (Test-Path -LiteralPath $installDirectory) {
    if ((Test-Path -LiteralPath $versionFile) -and
        (Get-Content -LiteralPath $versionFile -Raw).Trim() -eq $version -and
        (Test-Path -LiteralPath (Join-Path $installDirectory 'bin\rsync.exe')) -and
        (Test-Path -LiteralPath (Join-Path $installDirectory 'bin\ssh.exe'))) {
        Write-Host "cwRsync $version is already installed at $installDirectory"
        & $cacheScript
        exit 0
    }
    throw "An existing cwRsync directory needs review before installation: $installDirectory"
}

New-Item -ItemType Directory -Path $toolsDirectory -Force | Out-Null
$stagingDirectory = Join-Path $toolsDirectory ('.cwrsync-install-' + [guid]::NewGuid().ToString('N'))
$toolsPath = [IO.Path]::GetFullPath($toolsDirectory).TrimEnd('\') + '\'
$stagingPath = [IO.Path]::GetFullPath($stagingDirectory)
$installPath = [IO.Path]::GetFullPath($installDirectory)
if (-not $stagingPath.StartsWith($toolsPath, [StringComparison]::OrdinalIgnoreCase) -or
    -not $installPath.StartsWith($toolsPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Installation paths must stay within $toolsDirectory"
}

New-Item -ItemType Directory -Path $stagingDirectory | Out-Null
try {
    $archivePath = Join-Path $stagingDirectory $archiveName
    Invoke-WebRequest -Uri $downloadUrl -OutFile $archivePath -UseBasicParsing
    $actualHash = (Get-FileHash -LiteralPath $archivePath -Algorithm SHA256).Hash
    if ($actualHash -ne $expectedHash) {
        throw "cwRsync download checksum mismatch: $actualHash"
    }

    $extractedDirectory = Join-Path $stagingDirectory 'extracted'
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extractedDirectory
    $packageDirectory = Join-Path $extractedDirectory "cwrsync_${version}_x64_free"
    if (-not (Test-Path -LiteralPath $packageDirectory)) {
        $packageDirectory = $extractedDirectory
    }
    foreach ($file in @('bin\rsync.exe', 'bin\ssh.exe', 'bin\cygwin1.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $packageDirectory $file))) {
            throw "cwRsync archive is missing $file"
        }
    }

    if (Test-Path -LiteralPath $installDirectory) {
        throw "Installation directory appeared while downloading: $installDirectory"
    }
    $packagePath = (Resolve-Path -LiteralPath $packageDirectory).Path
    if (-not $packagePath.StartsWith($stagingPath + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Extracted package is outside $stagingDirectory"
    }
    Move-Item -LiteralPath $packagePath -Destination $installDirectory
    Set-Content -LiteralPath $versionFile -Value $version -NoNewline
    Write-Host "Installed cwRsync $version at $installDirectory"
}
finally {
    Remove-Item -LiteralPath $stagingDirectory -Recurse -Force
}

& $cacheScript
