# =============================================================================
#  Build the branded VibeFlow.exe (one-folder) with PyInstaller.
#
#  The executable embeds the VibeFlow icon and version metadata, so Windows
#  shows "VibeFlow" everywhere — including the microphone privacy indicator
#  ("Microphone in use by: VibeFlow") instead of "Python".
#
#  The speech model is NOT bundled (it is large); it downloads on first use into
#  %APPDATA%\VibeFlow\models. Output: release\VibeFlow\VibeFlow.exe
# =============================================================================

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPy)) {
    Write-Host "Run scripts\install.ps1 first." -ForegroundColor Red
    exit 1
}

Write-Host "Ensuring build tools (PyInstaller) ..." -ForegroundColor Yellow
& $VenvPy -m pip install --upgrade "pyinstaller>=6" --quiet

# Make sure the .ico exists (generated from the logo renderer).
$Ico = Join-Path $Root "src\vibeflow\resources\logos\vibeflow.ico"
if (-not (Test-Path $Ico)) {
    Write-Host "Generating application icon ..." -ForegroundColor Yellow
    & $VenvPy -c "from vibeflow import icons; icons.save_ico(r'$Ico')"
}
$VersionFile = Join-Path $Root "packaging\version_info.txt"

Write-Host "Building VibeFlow.exe (this takes a few minutes) ..." -ForegroundColor Yellow
& $VenvPy -m PyInstaller `
    --noconfirm `
    --clean `
    --name VibeFlow `
    --windowed `
    --icon "$Ico" `
    --version-file "$VersionFile" `
    --paths src `
    --collect-submodules vibeflow `
    --collect-data vibeflow.resources `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all tokenizers `
    --collect-all av `
    --collect-all onnxruntime `
    --collect-all comtypes `
    --collect-all noisereduce `
    --collect-all moonshine_onnx `
    --hidden-import tkinter `
    --distpath release `
    --workpath build\pyinstaller `
    --specpath build `
    scripts\launch.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed. See the messages above." -ForegroundColor Red
    exit 1
}

# --- Optional code signing ---------------------------------------------------
# To remove the Windows SmartScreen "Unknown publisher" warning, set:
#   $env:VIBEFLOW_PFX = "C:\path\to\codesign.pfx"
#   $env:VIBEFLOW_PFX_PASSWORD = "..."
# before building. Without these, signing is skipped (unsigned build). See
# docs\CODE_SIGNING.md for how to obtain a certificate.
function Invoke-CodeSign([string]$FilePath) {
    if (-not $env:VIBEFLOW_PFX) {
        Write-Host "  (code signing skipped - set VIBEFLOW_PFX to sign; see docs\CODE_SIGNING.md)" -ForegroundColor DarkGray
        return
    }
    $st = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($st) { $tool = $st.Source } else {
        $tool = Get-ChildItem "C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1 -ExpandProperty FullName
    }
    if (-not $tool) { Write-Host "  signtool not found (install the Windows SDK)." -ForegroundColor Yellow; return }
    & $tool sign /f "$env:VIBEFLOW_PFX" /p "$env:VIBEFLOW_PFX_PASSWORD" /fd SHA256 `
        /tr http://timestamp.digicert.com /td SHA256 "$FilePath"
    if ($LASTEXITCODE -eq 0) { Write-Host "  signed: $FilePath" -ForegroundColor Green }
}
Invoke-CodeSign (Join-Path $Root "release\VibeFlow\VibeFlow.exe")

Write-Host ""
Write-Host "Done: release\VibeFlow\VibeFlow.exe" -ForegroundColor Green
Write-Host "Tip: build the single-file installer with scripts\build_installer.ps1" -ForegroundColor Gray
