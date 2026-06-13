# Mnemo launcher (Windows / PowerShell). Idempotent: exits if already running.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$port = if ($env:MNEMO_PORT) { $env:MNEMO_PORT } else { "7575" }

# Already running? Don't start a second instance.
try {
    $h = Invoke-RestMethod "http://127.0.0.1:$port/api/health" -TimeoutSec 2
    if ($h.app -eq "mnemo") {
        Write-Host "Mnemo already running on http://127.0.0.1:$port" -ForegroundColor Yellow
        return
    }
} catch { }

$python = "C:\Program Files\Python311\python.exe"
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }

Write-Host "Starting Mnemo on http://127.0.0.1:$port ..." -ForegroundColor Cyan
& $python -m uvicorn app:app --host 127.0.0.1 --port $port
