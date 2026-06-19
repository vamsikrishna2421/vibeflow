# =============================================================================
#  VibeFlow launcher (with a console window, useful for seeing messages).
#  For everyday silent use, prefer "Start-VibeFlow.bat" in the main folder.
#  Any arguments are passed through, e.g.:  scripts\run.ps1 --doctor
# =============================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "VibeFlow is not installed yet." -ForegroundColor Red
    Write-Host "Please run 'Install-VibeFlow.bat' first." -ForegroundColor Red
    Read-Host "Press Enter to close"
    exit 1
}

& $VenvPy -m vibeflow @args
