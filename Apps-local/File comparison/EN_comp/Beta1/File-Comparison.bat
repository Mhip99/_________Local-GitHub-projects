@echo off
chcp 65001 >nul
cd /d "%~dp0"
title File Comparison (Beta1)

set "PS1=%~dp0Run-FileComparison.ps1"
if not exist "%PS1%" (
  echo [ERROR] Run-FileComparison.ps1 が見つかりません:
  echo   "%PS1%"
  pause & exit /b 1
)

echo ==================================================
echo    File Comparison ランチャー (Beta1)
echo ==================================================
echo  Run-FileComparison.ps1 を起動します。
echo  実行時に Fullset / Project を選択してください。
echo --------------------------------------------------

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
