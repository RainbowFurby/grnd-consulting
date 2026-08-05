# Running on Windows

## 1. Create the wrapper

Save this as `run-bot.bat` in the project folder, editing the path:

```bat
@echo off
cd /d C:\Users\YOUR_NAME\matcha-vendor-bot
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe -m bot.run
) else (
    python -m bot.run
)
```

Double-click it once to confirm it runs before scheduling it.

## 2. Schedule it

PowerShell, run as your normal user (not admin):

```powershell
$action  = New-ScheduledTaskAction -Execute "C:\Users\YOUR_NAME\matcha-vendor-bot\run-bot.bat"

$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
             -RepetitionInterval (New-TimeSpan -Minutes 90)

# StartWhenAvailable catches up on runs missed while the laptop was asleep.
$settings = New-ScheduledTaskSettingsSet `
              -StartWhenAvailable `
              -DontStopIfGoingOnBatteries `
              -AllowStartIfOnBatteries `
              -RandomDelay (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName "MatchaVendorBot" `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description "Watches FB groups for bazaar vendor calls"
```

## 3. Check and manage

```powershell
Get-ScheduledTask -TaskName "MatchaVendorBot"
Get-ScheduledTaskInfo -TaskName "MatchaVendorBot"   # last run time and result

Start-ScheduledTask -TaskName "MatchaVendorBot"     # run now
Unregister-ScheduledTask -TaskName "MatchaVendorBot" -Confirm:$false
```

The bot's own log is at `data\bot.log` regardless of what Task Scheduler
reports.
