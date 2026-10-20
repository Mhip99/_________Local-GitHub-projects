@echo off
chcp 65001 >nul
cd /d "%~dp0"
title JA Version Check

set "PS1=%~dp0Run-JAVersionCheck.ps1"
if not exist "%PS1%" (
  echo [ERROR] Run-JAVersionCheck.ps1 が見つかりません:
  echo   "%PS1%"
  pause & exit /b 1
)

rem PowerShell 7 (pwsh) を優先。無ければ Windows PowerShell を使用。
where pwsh >nul 2>nul
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
) else (
  pwsh -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
)

echo.
echo --------------------------------------------------
echo 完了しました。何かキーを押すとウィンドウを閉じます。
pause >nul
