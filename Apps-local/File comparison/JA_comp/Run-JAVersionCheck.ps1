<#
.SYNOPSIS
  JA Version Check ランチャー。日本語版が英語版と同じバージョンかをチェックする。
.DESCRIPTION
  ja_version_check.py を呼び出す。起動時に説明を表示→実行確認→(任意)Published JA パス入力→実行。
.EXAMPLE
  .\Run-JAVersionCheck.ps1
.EXAMPLE
  .\Run-JAVersionCheck.ps1 -Published "C:\...\published-ja"
#>
param(
    [string]$En,
    [string]$Ja,
    [string]$Published,
    [string]$Results,
    [switch]$NoTM
)

$py = "C:\Program Files\Python311\python.exe"
$script = Join-Path $PSScriptRoot "ja_version_check.py"
if (-not (Test-Path $py))     { Write-Error "Python が見つかりません: $py"; exit 1 }
if (-not (Test-Path $script)) { Write-Error "スクリプトが見つかりません: $script"; exit 1 }

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "   JA Version Check  (日本語版バージョンチェック)" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "最新フォルダの日本語版が英語版と同じバージョンかをチェックします。"
Write-Host "（英語版が更新されたのに日本語版が古いままの記事を検出）"
Write-Host ""
Write-Host " 1. Current の英語版(EN)と日本語版(JA)を比較し、英語版と同じバージョンの"
Write-Host "    日本語版が存在するかを判定（対応付け: 同名→Title(TM訳)→内容(TM)。テキストのみ）。"
Write-Host " 2. 日本語版のみ(英語版なし)・英語版のみ(未ローカライズ)を抽出。"
Write-Host "    Published Japanese version のパスを入力すると、それも比較対象に含めます。"
Write-Host ""
Write-Host " 判定: Match rate=TMカバレッジ率のみ。>=99%=Identical / <99%=EN Updated(要再翻訳) / <15%=Mismatch。"
Write-Host "       日付・画像・URLは判定に不使用。"
Write-Host " 結果: __Results\JA version\JA_version-YYYYMMDD.xlsx (シート: Compare / Data)。EN Updated が再翻訳対象。"
Write-Host "--------------------------------------------------"

$go = (Read-Host "実行しますか? (Y/N)").Trim()
if ($go -notmatch '^(y|Y)') { Write-Host "キャンセルしました。"; exit 0 }

if (-not $Published) {
    $Published = (Read-Host "Published Japanese version フォルダー (無ければ Enter)").Trim().Trim('"')
}

$cmd = @($script)
if ($En)        { $cmd += @("--en", $En) }
if ($Ja)        { $cmd += @("--ja", $Ja) }
if ($Published) { $cmd += @("--published", $Published) }
if ($Results)   { $cmd += @("--results", $Results) }
if ($NoTM)      { $cmd += "--no-tm" }

Write-Host ""
Write-Host "実行中... (TM索引の初回作成時は数十秒かかります)" -ForegroundColor Cyan
& $py @cmd
