param(
    [string]$SourcePath = 'D:\Quant',
    [string]$BackupRoot = 'D:\QuantBackup\Quant',
    [int]$KeepLatest = 1,
    [int]$MaxAgeDays = 1
)

$ErrorActionPreference = 'Stop'

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backupScript = Join-Path $scriptRoot 'backup_quant.ps1'
$validateScript = Join-Path $scriptRoot 'validate_quant_backup.ps1'
$logDir = Join-Path $BackupRoot 'logs'
$wrapperLog = Join-Path $logDir ("quant_daily_backup_wrapper_{0}.log" -f (Get-Date -Format 'yyyyMM'))

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-WrapperLog([string]$Message) {
    $line = "[{0}] {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $wrapperLog -Value $line -Encoding UTF8
}

try {
    Write-WrapperLog "Daily backup wrapper started. source=$SourcePath backup_root=$BackupRoot"

    & $backupScript -SourcePath $SourcePath -BackupRoot $BackupRoot -KeepLatest $KeepLatest
    if ($LASTEXITCODE -ne 0) {
        throw "backup_quant.ps1 failed with exit code $LASTEXITCODE"
    }

    $validationJson = & $validateScript -BackupRoot $BackupRoot -MaxAgeDays $MaxAgeDays
    $validationJson | Add-Content -Path $wrapperLog -Encoding UTF8
    if ($LASTEXITCODE -ne 0) {
        throw "validate_quant_backup.ps1 failed with exit code $LASTEXITCODE"
    }

    Write-WrapperLog "Daily backup wrapper completed successfully."
    exit 0
} catch {
    Write-WrapperLog "Daily backup wrapper failed: $($_.Exception.Message)"
    Write-Error $_
    exit 1
}
