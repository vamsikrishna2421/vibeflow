# =============================================================================
#  Build the single-file VibeFlow installer (VibeFlowSetup.exe).
#
#  Steps:
#    1. Build the branded VibeFlow.exe (PyInstaller) via build_exe.ps1.
#    2. Wrap it into a next-next-finish installer with Inno Setup.
#
#  Requires Inno Setup 6:  https://jrsoftware.org/isdl.php
#  (or: winget install JRSoftware.InnoSetup)
#
#  Output: release\installer\VibeFlowSetup.exe  (the one file you give testers)
# =============================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

# --- 1. Build the executable ------------------------------------------------
Write-Host "Step 1/2: building VibeFlow.exe ..." -ForegroundColor Cyan
& (Join-Path $PSScriptRoot "build_exe.ps1")
if ($LASTEXITCODE -ne 0) { exit 1 }

# --- 2. Locate Inno Setup compiler -----------------------------------------
$Iscc = $null
$cmd = Get-Command iscc -ErrorAction SilentlyContinue
if ($cmd) { $Iscc = $cmd.Source }
foreach ($p in @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe")) {
    if (-not $Iscc -and (Test-Path $p)) { $Iscc = $p }
}
if (-not $Iscc) {
    Write-Host ""
    Write-Host "Inno Setup (ISCC.exe) was not found." -ForegroundColor Red
    Write-Host "Install it once from https://jrsoftware.org/isdl.php" -ForegroundColor Red
    Write-Host "or run:  winget install JRSoftware.InnoSetup" -ForegroundColor Red
    Write-Host "Then re-run this script." -ForegroundColor Red
    exit 1
}

# --- 3. Compile the installer ----------------------------------------------
Write-Host "Step 2/2: building the installer with Inno Setup ..." -ForegroundColor Cyan
& $Iscc "installer\vibeflow.iss"
if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Done: release\installer\VibeFlowSetup.exe" -ForegroundColor Green
    Write-Host "Give that single file to your testers - double-click, next, next, finish." -ForegroundColor Green
} else {
    Write-Host "Installer build failed. See the messages above." -ForegroundColor Red
    exit 1
}
