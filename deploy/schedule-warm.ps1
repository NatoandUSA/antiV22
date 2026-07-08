# schedule-warm.ps1 - register warm-sync.ps1 in Windows Task Scheduler so this PC
# refreshes + syncs the keyword cache automatically every N hours (default 6).
#
#   powershell -ExecutionPolicy Bypass -File deploy\schedule-warm.ps1            # every 6h
#   powershell -ExecutionPolicy Bypass -File deploy\schedule-warm.ps1 -Hours 3   # every 3h
#   powershell -ExecutionPolicy Bypass -File deploy\schedule-warm.ps1 -Remove    # delete it
#
# Runs only while you're logged in (no stored password needed). "Run task as soon
# as possible after a missed start" is enabled, so if the PC was asleep at the slot
# it fires shortly after you're back — handy across the midnight date rollover.
param(
  [int]$Hours = 6,
  [switch]$Remove
)
$ErrorActionPreference = "Stop"
$TaskName = "EtsyAgent-WarmSync"
$repo   = Split-Path $PSScriptRoot -Parent
$script = Join-Path $repo "deploy\warm-sync.ps1"

if ($Remove) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Removed scheduled task '$TaskName'."
  return
}

if ($Hours -lt 1 -or $Hours -gt 24) { throw "-Hours must be 1..24" }

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`"" -WorkingDirectory $repo
# Repeat every N hours, starting a couple minutes from now. Use a large FINITE
# duration (~27 yrs) - [TimeSpan]::MaxValue serializes to an out-of-range task XML.
$start   = (Get-Date).AddMinutes(2)
$trigger = New-ScheduledTaskTrigger -Once -At $start `
  -RepetitionInterval (New-TimeSpan -Hours $Hours) -RepetitionDuration (New-TimeSpan -Days 9999)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -DontStopOnIdleEnd -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
  -Settings $settings -Description "Refresh YTrends keyword cache + sync to VPS every $Hours h" -Force | Out-Null

Write-Host "Scheduled '$TaskName' every $Hours h (first run ~$($start.ToString('HH:mm')))."
Write-Host "Check it:   Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo"
Write-Host "Run now:    Start-ScheduledTask -TaskName $TaskName"
Write-Host "NOTE: needs passwordless SSH to the VPS, or the sync step will hang waiting for a password."
