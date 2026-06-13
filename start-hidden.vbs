' Launch Mnemo with no visible console window (used by autostart + shortcut).
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = "F:\Apps\Mnemo"
sh.Run "powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""F:\Apps\Mnemo\run.ps1""", 0, False
