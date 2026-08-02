# Build the Windows desktop app: dist\FRIDAY\ (app) and dist\FRIDAY-Setup-<version>.exe.
# Run from the repo root:  powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
$ErrorActionPreference = 'Stop'

python -m PyInstaller --noconfirm friday.spec
if (-not $?) { throw 'PyInstaller failed' }

# winget's Inno Setup installs per-user under %LOCALAPPDATA%; the classic installer is in Program Files.
$iscc = @(
  "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
  'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { $iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source }
if (-not $iscc) {
  Write-Host 'App built to dist\FRIDAY. Inno Setup not found — install it for the installer:'
  Write-Host '  winget install JRSoftware.InnoSetup'
  exit 0
}

& $iscc 'installer\friday.iss'
Write-Host 'Done. Installer in dist\.'
