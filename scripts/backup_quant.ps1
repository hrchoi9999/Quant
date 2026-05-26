param(
    [string]$SourcePath = 'D:\Quant',
    [string]$BackupRoot = 'D:\QuantBackup\Quant',
    [int]$KeepLatest = 1
)

$ErrorActionPreference = 'Stop'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$logDir = Join-Path $BackupRoot 'logs'
$logPath = Join-Path $logDir ("quant_backup_{0}.log" -f (Get-Date -Format 'yyyyMM'))
$stagingRoot = Join-Path $BackupRoot '_staging'
$stagingPath = Join-Path $stagingRoot "Quant_$timestamp"
$zipPath = Join-Path $BackupRoot "Quant_$timestamp.zip"
$bundlePath = Join-Path $BackupRoot "Quant_git_$timestamp.bundle"
$latestInfo = Join-Path $BackupRoot 'latest_quant_backup.txt'

function Write-Log([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $logPath -Value $line -Encoding UTF8
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
New-Item -ItemType Directory -Force -Path $stagingRoot | Out-Null

Write-Log "Backup started. source=$SourcePath keep_latest=$KeepLatest"

if (Test-Path $stagingPath) { Remove-Item -Recurse -Force $stagingPath }
New-Item -ItemType Directory -Force -Path $stagingPath | Out-Null

$excludeDirs = @(
    '.git',
    '.pytest_cache',
    '.ruff_cache',
    '__pycache__',
    '_tmp',
    'htmlcov',
    'venv64'
)
$xdArgs = foreach ($item in $excludeDirs) { '/XD'; (Join-Path $SourcePath $item) }

$robocopyArgs = @(
    $SourcePath,
    $stagingPath,
    '/E',
    '/R:1',
    '/W:1',
    '/NFL',
    '/NDL',
    '/NJH',
    '/NJS',
    '/NP'
) + $xdArgs

& robocopy @robocopyArgs | Out-Null
$rc = $LASTEXITCODE
if ($rc -gt 7) {
    Write-Log "Backup failed during robocopy. exit_code=$rc"
    throw "robocopy failed with exit code $rc"
}

if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $stagingPath,
    $zipPath,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $true
)

$gitHead = 'not-a-git-repo'
$bundleCreated = $false
if (Test-Path (Join-Path $SourcePath '.git')) {
    try {
        $gitHead = (& git -c safe.directory=$SourcePath -C $SourcePath rev-parse --short HEAD).Trim()
        if (Test-Path $bundlePath) { Remove-Item -Force $bundlePath }
        & git -c safe.directory=$SourcePath -C $SourcePath bundle create $bundlePath --all | Out-Null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $bundlePath)) {
            $bundleCreated = $true
        }
    } catch {
        $gitHead = 'bundle-create-failed'
        Write-Log "Git bundle creation failed: $($_.Exception.Message)"
    }
}

@(
    "backup_created_at=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')",
    "source=$SourcePath",
    "zip=$zipPath",
    "git_head=$gitHead",
    "git_bundle=$bundlePath",
    "git_bundle_created=$bundleCreated",
    "keep_latest=$KeepLatest",
    "excluded_dirs=$($excludeDirs -join ',')"
) | Set-Content -Path $latestInfo -Encoding UTF8

$oldBackups = Get-ChildItem -Path $BackupRoot -Filter 'Quant_*.zip' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLatest

foreach ($old in $oldBackups) {
    Remove-Item -Force $old.FullName
    Write-Log "Deleted old backup: $($old.Name)"
}

$oldBundles = Get-ChildItem -Path $BackupRoot -Filter 'Quant_git_*.bundle' |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $KeepLatest

foreach ($old in $oldBundles) {
    Remove-Item -Force $old.FullName
    Write-Log "Deleted old git bundle: $($old.Name)"
}

Remove-Item -Recurse -Force $stagingPath
Write-Log "Backup completed. zip=$zipPath git_head=$gitHead git_bundle_created=$bundleCreated"
Write-Output "Backup created: $zipPath"
if ($bundleCreated) {
    Write-Output "Git bundle created: $bundlePath"
}
