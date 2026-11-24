@echo off
chcp 65001 >nul
set "LTDIR=%LOCALAPPDATA%\Kotonoha-LT"
echo LanguageTool + ポータブルJRE を "%LTDIR%" に導入します（約290MB・数分）。
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=$env:LOCALAPPDATA+'\Kotonoha-LT'; New-Item -ItemType Directory -Force -Path $d ^| Out-Null; $ProgressPreference='SilentlyContinue'; Write-Host 'JRE をダウンロード...'; Invoke-WebRequest 'https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jre/hotspot/normal/eclipse?project=jdk' -OutFile ($d+'\jre.zip'); Expand-Archive ($d+'\jre.zip') $d -Force; Write-Host 'LanguageTool をダウンロード...'; Invoke-WebRequest 'https://languagetool.org/download/LanguageTool-stable.zip' -OutFile ($d+'\lt.zip'); Expand-Archive ($d+'\lt.zip') $d -Force; Remove-Item ($d+'\jre.zip'),($d+'\lt.zip') -Force; Write-Host '完了: '+$d"
pause
