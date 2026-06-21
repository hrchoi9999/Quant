param(
    [string]$BackupRoot = 'D:\QuantBackup\Quant',
    [int]$MaxAgeDays = 3
)

$ErrorActionPreference = 'Stop'

function New-Result([bool]$Ok, [string[]]$Errors, [object]$Details) {
    [pscustomobject]@{
        ok = $Ok
        errors = $Errors
        details = $Details
    }
}

$errors = New-Object System.Collections.Generic.List[string]

if (-not (Test-Path -LiteralPath $BackupRoot)) {
    $errors.Add("Backup root not found: $BackupRoot")
    New-Result $false $errors @{} | ConvertTo-Json -Depth 6
    exit 1
}

$latestInfo = Join-Path $BackupRoot 'latest_quant_backup.txt'
$latestZipPath = $null
$latestBundlePath = $null
if (Test-Path -LiteralPath $latestInfo) {
    foreach ($line in Get-Content -LiteralPath $latestInfo) {
        if ($line -like 'zip=*') {
            $latestZipPath = $line.Substring(4)
        } elseif ($line -like 'git_bundle=*') {
            $latestBundlePath = $line.Substring(11)
        }
    }
}

$latestZip = if ($latestZipPath -and (Test-Path -LiteralPath $latestZipPath)) {
    Get-Item -LiteralPath $latestZipPath
} else {
    Get-ChildItem -LiteralPath $BackupRoot -Filter 'Quant_*.zip' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

if (-not $latestZip) {
    $errors.Add("No Quant_*.zip backup found under $BackupRoot")
    New-Result $false $errors @{} | ConvertTo-Json -Depth 6
    exit 1
}

$ageDays = ((Get-Date) - $latestZip.LastWriteTime).TotalDays
if ($ageDays -gt $MaxAgeDays) {
    $errors.Add(("Latest backup is stale: {0:n2} days old" -f $ageDays))
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zipEntries = @()
$zipReadable = $false
try {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($latestZip.FullName)
    try {
        $zipEntries = $zip.Entries
        $zipReadable = $true
        $normalizedNames = $zipEntries | ForEach-Object { $_.FullName.Replace('\', '/') }
        $firstName = $normalizedNames | Where-Object { $_ } | Select-Object -First 1
        $rootPrefix = if ($firstName -and $firstName.Contains('/')) {
            $firstName.Split('/')[0] + '/'
        } else {
            ''
        }
        $requiredPrefixes = @(
            $rootPrefix,
            ($rootPrefix + 'scripts/'),
            ($rootPrefix + 'src/'),
            ($rootPrefix + 'docs/'),
            ($rootPrefix + 'data/')
        )
        foreach ($prefix in $requiredPrefixes) {
            $exists = $normalizedNames | Where-Object { $_.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase) } | Select-Object -First 1
            if (-not $exists) {
                $errors.Add("Required ZIP prefix missing: $prefix")
            }
        }
    } finally {
        $zip.Dispose()
    }
} catch {
    $errors.Add("Unable to read latest ZIP backup: $($_.Exception.Message)")
}

$latestBundle = if ($latestBundlePath -and (Test-Path -LiteralPath $latestBundlePath)) {
    Get-Item -LiteralPath $latestBundlePath
} else {
    Get-ChildItem -LiteralPath $BackupRoot -Filter 'Quant_git_*.bundle' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

$bundleOk = $false
if (-not $latestBundle) {
    $errors.Add("No Quant_git_*.bundle found under $BackupRoot")
} else {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $verifyOutput = & git bundle verify $latestBundle.FullName 2>&1
    $ErrorActionPreference = $previousErrorActionPreference
    if ($LASTEXITCODE -eq 0) {
        $bundleOk = $true
    } else {
        $errors.Add("Git bundle verify failed: $($verifyOutput -join ' ')")
    }
}

$details = [pscustomobject]@{
    backup_root = $BackupRoot
    latest_zip = $latestZip.FullName
    latest_zip_bytes = $latestZip.Length
    latest_zip_last_write = $latestZip.LastWriteTime.ToString('yyyy-MM-dd HH:mm:ss')
    latest_zip_age_days = [math]::Round($ageDays, 3)
    zip_readable = $zipReadable
    zip_entry_count = $zipEntries.Count
    latest_git_bundle = if ($latestBundle) { $latestBundle.FullName } else { $null }
    latest_git_bundle_bytes = if ($latestBundle) { $latestBundle.Length } else { $null }
    git_bundle_ok = $bundleOk
}

$ok = $errors.Count -eq 0
New-Result $ok $errors.ToArray() $details | ConvertTo-Json -Depth 6
if (-not $ok) {
    exit 1
}
