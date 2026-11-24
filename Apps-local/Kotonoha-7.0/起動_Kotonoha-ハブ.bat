@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kotonoha Hub (Dashboard)
set "PY=python"
where python >nul 2>nul || set "PY=py"
rem --- 既定パス（マシン非依存）。環境別の上書きは _kotonoha-paths.bat（任意・Git管理外）で set CACHE= / set LTDIR= ---
set "CACHE=%~dp0_Index"
set "LTDIR=%LOCALAPPDATA%\Kotonoha-LT"
if exist "%~dp0_kotonoha-paths.bat" call "%~dp0_kotonoha-paths.bat"
rem --- LanguageTool（英語リアルタイム文法・任意）: 存在時のみ起動（版フォルダはワイルドカード検出・ハブ終了で一緒に停止）---
set "JREEXE="
set "LTJAR="
for /d %%J in ("%LTDIR%\jdk*") do set "JREEXE=%%J\bin\java.exe"
for /d %%L in ("%LTDIR%\LanguageTool-*") do set "LTJAR=%%L\languagetool-server.jar"
if exist "%JREEXE%" if exist "%LTJAR%" start "LanguageTool" /b "%JREEXE%" -cp "%LTJAR%" org.languagetool.server.HTTPServer --port 8081
echo.
echo  Starting Kotonoha Hub... a browser window will open automatically.
echo  To stop: press Ctrl+C in this window, or just close it.
echo.
"%PY%" "%~dp0projects.py" serve --cache-dir "%CACHE%" --template "%~dp0TM-Match-Explorer-demo.html" --engine "%~dp0tm_match_analysis.py"
echo.
echo  Server stopped.
pause
