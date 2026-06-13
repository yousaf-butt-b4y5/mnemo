# Run ONCE to make Mnemo start automatically (hidden) when you log in.
# Idempotent — safe to run again; it just refreshes the shortcut.
# To undo: delete the shortcut from the Startup folder (path printed below).

$startup = [Environment]::GetFolderPath('Startup')
$lnkPath = Join-Path $startup 'Mnemo.lnk'
$target  = 'F:\Apps\Mnemo\start-hidden.vbs'

if (-not (Test-Path $target)) { Write-Error "Missing $target"; return }

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnkPath)
$sc.TargetPath = 'wscript.exe'
$sc.Arguments  = "`"$target`""
$sc.WorkingDirectory = 'F:\Apps\Mnemo'
$sc.Description = 'Start Mnemo note hub (hidden) at logon'
$sc.Save()

Write-Host "Autostart installed:" -ForegroundColor Green
Write-Host "  $lnkPath"
Write-Host "Mnemo will start hidden at each logon. Open it at http://localhost:7575"
Write-Host "To disable later: delete that .lnk file." -ForegroundColor DarkGray
