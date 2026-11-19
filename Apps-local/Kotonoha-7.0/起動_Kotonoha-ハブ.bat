@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kotonoha Hub (Dashboard)
set "PY=python"
where python >nul 2>nul || set "PY=py"
rem LanguageTool (英語リアルタイム文法・ローカル) を起動（存在時のみ・バックグラウンド・ハブ終了で一緒に停止）
set "LTDIR=%LOCALAPPDATA%\Kotonoha-LT"
if exist "%LTDIR%\LanguageTool-6.6\languagetool-server.jar" start "LanguageTool" /b "%LTDIR%\jdk-21.0.13+9-jre\bin\java.exe" -cp "%LTDIR%\LanguageTool-6.6\languagetool-server.jar" org.languagetool.server.HTTPServer --port 8081
echo.
echo  Starting Kotonoha Hub... a browser window will open automatically.
echo  To stop: press Ctrl+C in this window, or just close it.
echo.
"%PY%" "%~dp0projects.py" serve --cache-dir "C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\Kotonoha\Index" --template "%~dp0TM-Match-Explorer-demo.html" --engine "%~dp0tm_match_analysis.py"
echo.
echo  Server stopped.
pause
