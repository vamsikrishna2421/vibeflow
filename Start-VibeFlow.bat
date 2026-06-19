@echo off
rem ===========================================================================
rem  Double-click this file to start VibeFlow.
rem  A small microphone icon appears near the clock (system tray).
rem  Press Ctrl+Win, speak, then press it again.
rem ===========================================================================
set "VFPYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%VFPYW%" (
  echo.
  echo VibeFlow is not installed yet.
  echo Please double-click "Install-VibeFlow.bat" first.
  echo.
  pause
  exit /b 1
)
start "VibeFlow" "%VFPYW%" -m vibeflow
