<#
.SYNOPSIS
  Project 比較を実行する専用ランチャー（モード固定：Project）。
.DESCRIPTION
  file_compare_fullset.py を --label Project で呼び出します。
  Last translated フォルダーのパスを引数で渡すか、未指定の場合は実行時に入力を求めます。
  リポジトリのルートを指定した場合は s\article を自動採用します。
.EXAMPLE
  .\Run-Project.ps1
.EXAMPLE
  .\Run-Project.ps1 -LastTranslated "C:\...\domo-documentation-hub-main-0427"
.EXAMPLE
  # 翻訳対象の文字列だけを変更とみなす
  .\Run-Project.ps1 -LastTranslated "C:\...\s\article" -TranslatableOnly
#>
param(
    [string]$LastTranslated,
    [string]$Current,
    [string]$Results,
    [switch]$TranslatableOnly
)

$Mode = "Project"
$py = "C:\Program Files\Python311\python.exe"
$script = Join-Path $PSScriptRoot "file_compare_fullset.py"

if (-not (Test-Path $py))     { Write-Error "Python が見つかりません: $py"; exit 1 }
if (-not (Test-Path $script)) { Write-Error "スクリプトが見つかりません: $script"; exit 1 }

if (-not $LastTranslated) {
    $LastTranslated = Read-Host "Last translated version ($Mode) フォルダーのフルパスを入力してください"
}
$LastTranslated = $LastTranslated.Trim().Trim('"')
if (-not (Test-Path $LastTranslated)) { Write-Error "フォルダーが見つかりません: $LastTranslated"; exit 1 }

# 前回翻訳版の対象は英語ソースの s\article。優先順: (1)直下の s\article (2)指定フォルダー自体に.mdx (3)配下を再帰検索
$direct = Join-Path $LastTranslated "s\article"
$hasMdx = Get-ChildItem -LiteralPath $LastTranslated -Filter *.mdx -File -ErrorAction SilentlyContinue | Select-Object -First 1
if (Test-Path -LiteralPath $direct) {
    $LastTranslated = $direct
    Write-Host "s\article を自動採用: $LastTranslated" -ForegroundColor DarkGray
} elseif ($hasMdx) {
    # 指定フォルダー自体が article フォルダー（.mdx を直接含む）→ そのまま使用
} else {
    $found = @(Get-ChildItem -LiteralPath $LastTranslated -Directory -Recurse -Filter "article" -ErrorAction SilentlyContinue |
               Where-Object { $_.Parent.Name -ieq "s" }) | Sort-Object { $_.FullName.Length }
    if ($found.Count -eq 0) {
        Write-Error "指定フォルダーの配下に s\article が見つかりません: $LastTranslated"; exit 1
    }
    if ($found.Count -gt 1) {
        Write-Host ("s\article が複数見つかりました。最上位を採用します (他 " + ($found.Count - 1) + " 件):") -ForegroundColor Yellow
        $found | ForEach-Object { Write-Host ("  - " + $_.FullName) -ForegroundColor DarkGray }
    }
    $LastTranslated = $found[0].FullName
    Write-Host "s\article を自動採用: $LastTranslated" -ForegroundColor DarkGray
}

$cmdArgs = @($script, $LastTranslated, "--label", $Mode)
if ($Current) { $cmdArgs += @("--current", $Current) }
if ($Results) { $cmdArgs += @("--results", $Results) }
if ($TranslatableOnly) { $cmdArgs += "--translatable-only" }

Write-Host "Project 比較を開始します..." -ForegroundColor Cyan
& $py @cmdArgs
