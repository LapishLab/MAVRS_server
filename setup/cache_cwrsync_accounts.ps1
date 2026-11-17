$ErrorActionPreference = 'Stop'

$repository = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$tools = Join-Path $repository '.tools'
$cwrsync = Join-Path $tools 'cwrsync'
$bin = Join-Path $cwrsync 'bin'
$etc = Join-Path $cwrsync 'etc'
$nsswitch = Join-Path $etc 'nsswitch.conf'
$signaturePath = Join-Path $etc 'account-cache.signature'
$accountTools = Join-Path $cwrsync 'account-tools'
$toolNames = @('id.exe', 'getent.exe', 'cygargp-0.dll')
$toolsInstalled = @($toolNames | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $accountTools $_))
}).Count -eq 0

foreach ($file in @((Join-Path $bin 'rsync.exe'), (Join-Path $bin 'cygwin1.dll'), $nsswitch)) {
    if (-not (Test-Path -LiteralPath $file)) {
        throw "Install cwRsync with setup/install_cwrsync.ps1 first: missing $file"
    }
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$groupSids = @($identity.Groups | ForEach-Object { $_.Value } | Sort-Object)
$identityText = (@($identity.User.Value, $env:USERDOMAIN, $env:USERNAME, $env:USERPROFILE) + $groupSids) -join "`n"
$hashBytes = [Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($identityText))
$signature = [BitConverter]::ToString($hashBytes).Replace('-', '')
$config = [IO.File]::ReadAllText($nsswitch)
if ($toolsInstalled -and
    (Test-Path -LiteralPath (Join-Path $etc 'passwd')) -and
    (Test-Path -LiteralPath (Join-Path $etc 'group')) -and
    (Test-Path -LiteralPath $signaturePath) -and
    $config -match '(?m)^passwd:[ \t]*files[ \t]*\r?$' -and
    $config -match '(?m)^group:[ \t]*files[ \t]*\r?$' -and
    [IO.File]::ReadAllText($signaturePath).Trim() -eq $signature) {
    Write-Host 'cwRsync account cache is current.'
    return
}

$stage = Join-Path $tools ('cwrsync-accounts-' + [guid]::NewGuid().ToString('N'))
$toolsPath = [IO.Path]::GetFullPath($tools).TrimEnd('\') + '\'
$stagePath = [IO.Path]::GetFullPath($stage)
if (-not $stagePath.StartsWith($toolsPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Temporary path is outside $tools"
}

$files = @{
    'nsswitch.conf' = $nsswitch
    'passwd' = Join-Path $etc 'passwd'
    'group' = Join-Path $etc 'group'
    'account-cache.signature' = $signaturePath
}
$original = @{}
foreach ($name in $files.Keys) {
    if (Test-Path -LiteralPath $files[$name]) {
        $original[$name] = [IO.File]::ReadAllBytes($files[$name])
    } else {
        $original[$name] = $null
    }
}

$utf8 = New-Object Text.UTF8Encoding($false)
$oldPath = $env:PATH
$complete = $false
New-Item -ItemType Directory -Path $stage | Out-Null
try {
    if (-not $toolsInstalled) {
        $packages = @(
            @('coreutils/coreutils-9.6-1.tar.xz', 'usr/bin/id.exe'),
            @('getent/getent-2.18.90-5.tar.xz', 'usr/bin/getent.exe'),
            @('libargp/libargp-20250917-2-x86_64.tar.xz', 'usr/bin/cygargp-0.dll')
        )
        foreach ($package in $packages) {
            $archive = Join-Path $stage ([IO.Path]::GetFileName($package[0]))
            Invoke-WebRequest -Uri "https://gcc.gnu.org/ftp/cygwin/x86_64/release/$($package[0])" `
                -OutFile $archive -UseBasicParsing -TimeoutSec 60
            & tar.exe -xf $archive -C $stage $package[1]
            if ($LASTEXITCODE -ne 0) { throw "Could not extract $($package[1])" }
        }
        New-Item -ItemType Directory -Path $accountTools -Force | Out-Null
        foreach ($name in $toolNames) {
            Copy-Item -LiteralPath (Join-Path $stage "usr\bin\$name") -Destination $accountTools -Force
        }
    }

    # Query Windows directly so a refresh does not reuse stale file entries.
    $base = ([IO.File]::ReadAllText($nsswitch) -split '\r?\n' |
        Where-Object { $_ -notmatch '^\s*(passwd|group):' }) -join "`n"
    $base = $base.TrimEnd("`r", "`n")
    [IO.File]::WriteAllText($nsswitch, "$base`npasswd: db`ngroup: db`n", $utf8)

    $env:PATH = "$accountTools;$bin;$oldPath"
    $id = Join-Path $accountTools 'id.exe'
    $getent = Join-Path $accountTools 'getent.exe'
    $uid = & $id -u
    if ($LASTEXITCODE -ne 0 -or $uid -notmatch '^\d+$') { throw 'Could not read the current user ID' }
    $gids = @((& $id -G) -split '\s+' | Where-Object { $_ })
    if ($LASTEXITCODE -ne 0 -or $gids.Count -eq 0) { throw 'Could not read current groups' }
    $passwd = @(& $getent passwd $uid)
    if ($LASTEXITCODE -ne 0 -or $passwd.Count -ne 1 -or ($passwd[0] -split ':').Count -ne 7) {
        throw 'Could not resolve the current account'
    }
    $groups = @(& $getent group @gids)
    if ($LASTEXITCODE -ne 0 -or $groups.Count -ne $gids.Count) {
        throw "Resolved $($groups.Count) of $($gids.Count) current groups"
    }
    $resolvedGids = @($groups | ForEach-Object {
        $fields = $_ -split ':'
        if ($fields.Count -ne 4) { throw 'Invalid group entry' }
        $fields[2]
    })
    if (@(Compare-Object ($gids | Sort-Object -Unique) ($resolvedGids | Sort-Object -Unique)).Count -ne 0) {
        throw 'Account cache is missing a current group'
    }

    foreach ($name in @('nsswitch.conf', 'passwd', 'group')) {
        $backup = "$($files[$name]).before-account-cache"
        if ($null -ne $original[$name] -and -not (Test-Path -LiteralPath $backup)) {
            [IO.File]::WriteAllBytes($backup, $original[$name])
        }
    }
    [IO.File]::WriteAllLines($files['passwd'], $passwd, $utf8)
    [IO.File]::WriteAllLines($files['group'], $groups, $utf8)
    [IO.File]::WriteAllText($nsswitch, "$base`npasswd: files`ngroup: files`n", $utf8)
    [IO.File]::WriteAllText($signaturePath, $signature, $utf8)
    $complete = $true
    Write-Host "Cached the current account and $($groups.Count) groups for cwRsync."
}
finally {
    $env:PATH = $oldPath
    if (-not $complete) {
        foreach ($name in $files.Keys) {
            if ($null -eq $original[$name]) {
                Remove-Item -LiteralPath $files[$name] -Force -ErrorAction SilentlyContinue
            } else {
                [IO.File]::WriteAllBytes($files[$name], $original[$name])
            }
        }
    }
    Remove-Item -LiteralPath $stagePath -Recurse -Force
}
