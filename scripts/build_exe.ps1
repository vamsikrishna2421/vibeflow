# =============================================================================
#  Build a standalone VibeFlow.exe (advanced / optional).
#
#  Most people should just use the installer. This is for distributing a single
#  executable to machines without Python. The speech model is NOT bundled (it
#  is large); it downloads on first use into %APPDATA%\VibeFlow\models.
#
#  Output: release\VibeFlow\VibeFlow.exe
# =============================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "Run scripts\install.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Installing build tools (PyInstaller) ..." -ForegroundColor Yellow
& $VenvPy -m pip install --upgrade pyinstaller --quiet

Write-Host "Building VibeFlow.exe (this takes a few minutes) ..." -ForegroundColor Yellow
& $VenvPy -m PyInstaller `
    --noconfirm `
    --clean `
    --name VibeFlow `
    --windowed `
    --paths src `
    --collect-submodules vibeflow `
    --collect-data vibeflow.resources `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-all av `
    --collect-all onnxruntime `
    --hidden-import comtypes `
    --distpath release `
    --workpath build\pyinstaller `
    --specpath build `
    scripts\launch.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "Done. Find it at: release\VibeFlow\VibeFlow.exe" -ForegroundColor Green
} else {
    Write-Host "Build failed. See the messages above." -ForegroundColor Red
    exit 1
}
