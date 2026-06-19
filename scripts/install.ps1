# =============================================================================
#  VibeFlow installer (Windows)
#  Creates a private Python environment, installs everything VibeFlow needs,
#  and downloads the speech model so the app works fully offline afterwards.
#
#  Run it by double-clicking "Install-VibeFlow.bat" in the main folder, or:
#     powershell -ExecutionPolicy Bypass -File scripts\install.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

# Always operate from the project root (the folder above this script).
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host "   Installing VibeFlow - offline voice typing" -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host ""

# --- 1. Find Python ----------------------------------------------------------
Write-Host "[1/4] Looking for Python 3.9+ ..." -ForegroundColor Yellow
$PyCmd = $null
foreach ($candidate in @("py -3", "python", "python3")) {
    try {
        $parts = $candidate.Split(" ")
        $ver = & $parts[0] $parts[1..($parts.Length - 1)] --version 2>&1
        if ($LASTEXITCODE -eq 0 -and $ver -match "Python 3\.(9|1[0-9])") {
            $PyCmd = $candidate
            Write-Host "      Found: $ver" -ForegroundColor Green
            break
        }
    } catch { }
}
if (-not $PyCmd) {
    Write-Host "      Could not find Python 3.9 or newer." -ForegroundColor Red
    Write-Host "      Please install it from https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host "      During setup, tick 'Add python.exe to PATH'." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# --- 2. Create the virtual environment --------------------------------------
Write-Host "[2/4] Creating a private environment (.venv) ..." -ForegroundColor Yellow
$parts = $PyCmd.Split(" ")
if (-not (Test-Path ".venv")) {
    & $parts[0] $parts[1..($parts.Length - 1)] -m venv .venv
}
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "      Failed to create the environment." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# --- 3. Install VibeFlow + dependencies -------------------------------------
Write-Host "[3/4] Installing VibeFlow and its dependencies ..." -ForegroundColor Yellow
Write-Host "      (this can take a few minutes the first time)" -ForegroundColor DarkGray
& $VenvPy -m pip install --upgrade pip --quiet
& $VenvPy -m pip install -e . --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Dependency installation failed." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

# --- 4. Download the speech model (for offline use) -------------------------
Write-Host "[4/4] Downloading the speech model for offline use ..." -ForegroundColor Yellow
Write-Host "      (one-time download; needs internet just this once)" -ForegroundColor DarkGray
& $VenvPy -m vibeflow --download-model
if ($LASTEXITCODE -ne 0) {
    Write-Host "      Model download did not finish - no problem." -ForegroundColor DarkYellow
    Write-Host "      VibeFlow will download it automatically on first use." -ForegroundColor DarkYellow
}

Write-Host ""
Write-Host "=====================================================" -ForegroundColor Green
Write-Host "   VibeFlow is installed!" -ForegroundColor Green
Write-Host "=====================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  To start it: double-click 'Start-VibeFlow.bat'" -ForegroundColor White
Write-Host "  A small microphone icon appears near the clock." -ForegroundColor White
Write-Host "  Press Ctrl+Alt+Space, speak, press it again." -ForegroundColor White
Write-Host ""
Read-Host "Press Enter to close"
