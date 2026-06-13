# Back up Mnemo vaults (personal + work) to a timestamped folder.
# Your notes/secrets live in data/*.db (gitignored). Run this anytime,
# or schedule it later. Safe to run while Mnemo is running (WAL mode).
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$stamp  = Get-Date -Format "yyyy-MM-dd_HHmmss"
$dest   = Join-Path $PSScriptRoot "backups\$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null

$copied = 0
Get-ChildItem "$PSScriptRoot\data" -Filter "*.db" -ErrorAction SilentlyContinue | ForEach-Object {
    Copy-Item $_.FullName -Destination $dest
    $copied++
}

# Keep only the 20 most recent backups
Get-ChildItem "$PSScriptRoot\backups" -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending | Select-Object -Skip 20 |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

Write-Host "Backed up $copied vault file(s) -> $dest" -ForegroundColor Green
