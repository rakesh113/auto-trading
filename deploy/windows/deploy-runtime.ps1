# Creates or updates the runtime copy that the supervisor runs, separate from the development
# checkout. Development branches never affect what is recording or trading; only `main` does.
#
#   powershell -ExecutionPolicy Bypass -File deploy\windows\deploy-runtime.ps1 [-Ref origin/main] [-Restart]
#
# * Runtime folder: ..\auto-trading-run (a git worktree, detached at -Ref).
# * Its own .venv; its own .env (copied from this checkout the first time; edit it there after).
# * -Restart restarts the scheduled task so the new code is loaded. Avoid during market hours:
#   the recorder would miss a few seconds of data.

param(
    [string]$Ref = "origin/main",
    [switch]$Restart
)
$ErrorActionPreference = "Stop"
$repo = (Resolve-Path "$PSScriptRoot\..\..").Path
$run = Join-Path (Split-Path $repo -Parent) "auto-trading-run"

git -C $repo fetch --quiet origin
if (-not (Test-Path (Join-Path $run ".git"))) {
    git -C $repo worktree add --detach $run $Ref
} else {
    git -C $run checkout --quiet --detach $Ref
}
if (-not (Test-Path "$run\.venv\Scripts\python.exe")) {
    python -m venv "$run\.venv"
}
& "$run\.venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
& "$run\.venv\Scripts\python.exe" -m pip install --quiet -e $run
if (-not (Test-Path "$run\.env")) {
    Copy-Item "$repo\.env" "$run\.env"
    Write-Host "Copied .env into the runtime folder."
}
if (Test-Path "$repo\config\local.yaml") {
    Copy-Item "$repo\config\local.yaml" "$run\config\local.yaml" -Force
}
$rev = git -C $run rev-parse --short HEAD
Write-Host "Runtime at $run is now $Ref ($rev)."

& "$PSScriptRoot\install-tasks.ps1" -RunDir $run | Out-Null
Write-Host "Scheduled task now runs from $run."
if ($Restart) {
    Stop-ScheduledTask -TaskName AutoTrading-Supervisor -ErrorAction SilentlyContinue
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
        Where-Object { $_.CommandLine -like '*trader.apps.cli*' } |
        ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
    Start-ScheduledTask -TaskName AutoTrading-Supervisor
    Write-Host "Restarted AutoTrading-Supervisor."
}
