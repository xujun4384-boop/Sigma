# Javis Bridge keep-alive installer (Windows).
# Creates a Scheduled Task that runs relay_server.py at boot as SYSTEM,
# and a runner loop that restarts the Python process if it exits.
#
# Usage (in an elevated PowerShell):
#   .\install_service.ps1 -Key Sykes123
#   .\install_service.ps1 -Key Sykes123 -Port 8890 -Root C:\Javis_bridge
#
# Remove:
#   Unregister-ScheduledTask -TaskName JavisBridge -Confirm:$false

param(
    [string]$Root = "C:\Javis_bridge",
    [int]$Port = 8890,
    [string]$Key = "Sykes123",
    [string]$TaskName = "JavisBridge",
    [string]$PythonExe = ""
)
$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Please run this script in an elevated PowerShell (Run as Administrator)."
}
if ($Key -notmatch '^[A-Za-z0-9_.-]{8,}$') {
    throw "Key must be at least 8 characters and contain only letters, digits, dot, underscore or hyphen."
}

$server = Join-Path $Root "relay_server.py"
if (-not (Test-Path $server)) {
    throw "relay_server.py not found in $Root"
}
if (-not $PythonExe) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) {
        throw "python not found in PATH; pass -PythonExe C:\path\to\python.exe"
    }
    $PythonExe = $cmd.Source
}
if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

$runner = Join-Path $Root "run_relay_forever.ps1"
$log = Join-Path $Root "javis_bridge.log"
$runnerContent = @"
`$server = Join-Path '$Root' 'relay_server.py'
while (`$true) {
    & '$PythonExe' `$server --port $Port --key '$Key' --db (Join-Path '$Root' 'javis_bridge.db') --storage (Join-Path '$Root' 'javis_bridge_files') *>> (Join-Path '$Root' 'javis_bridge.log')
    Start-Sleep -Seconds 5
}
"@
Set-Content -Path $runner -Value $runnerContent -Encoding UTF8

$shell = Join-Path $PSHOME "powershell.exe"
$action = New-ScheduledTaskAction -Execute $shell -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runner`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -User "SYSTEM" `
    -RunLevel Highest `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' created (runs at boot as SYSTEM)."
Write-Host "Runner: $runner"
Write-Host "Log:    $log"
Write-Host ""
Write-Host "Stop the manual PowerShell instance, then start the task with:"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host "Check status with:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName'"
Write-Host "Remove with:"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
