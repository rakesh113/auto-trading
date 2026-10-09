# Registers the supervisor to start at logon and restart if it dies (design §10, laptop operation).
# Run once from an elevated PowerShell in the repo root:
#   powershell -ExecutionPolicy Bypass -File deploy\windows\install-tasks.ps1
# Remove with:  Unregister-ScheduledTask -TaskName "AutoTrading-Supervisor" -Confirm:$false

$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "venv not found at $python. Run: python -m venv .venv; .venv\Scripts\pip install -e .[dev]" }

$action = New-ScheduledTaskAction -Execute $python -Argument "-m trader.apps.cli supervise" -WorkingDirectory $repo
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "AutoTrading-Supervisor" -Action $action -Trigger $trigger -Settings $settings `
    -Description "auto-trading: recorder and services (restarts on crash)" -Force | Out-Null

# The recorder keeps the machine awake while it runs (SetThreadExecutionState). Also stop the
# lid/idle settings from sleeping the laptop when on AC power:
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Write-Host "Registered AutoTrading-Supervisor. Start now with: Start-ScheduledTask -TaskName AutoTrading-Supervisor"
Write-Host "Also set 'When I close the lid' = Do nothing (on AC) in Control Panel > Power Options."
