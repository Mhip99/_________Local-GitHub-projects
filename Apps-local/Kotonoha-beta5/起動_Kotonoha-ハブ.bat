@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Kotonoha Hub (Dashboard)
set "PY=python"
where python >nul 2>nul || set "PY=py"
echo.
echo  Starting Kotonoha Hub... a browser window will open automatically.
echo  To stop: press Ctrl+C in this window, or just close it.
echo.
"%PY%" "%~dp0projects.py" serve --cache-dir "C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\Kotonoha\Index" --template "%~dp0TM-Match-Explorer-demo.html" --engine "%~dp0tm_match_analysis.py"
echo.
echo  Server stopped.
pause
