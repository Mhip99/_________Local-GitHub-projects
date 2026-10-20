<#
.SYNOPSIS
  Current version と Last translated version の英語版ソースを比較し、Excel レポートを生成するランチャー。
  実行時に比較モード（Fullset / Project）を対話で選択します。
.DESCRIPTION
  file_compare_fullset.py を呼び出します。
  -Mode を指定しなかった場合は、実行時に Fullset / Project のどちらかを選択するよう求めます。
  Last translated フォルダーのパスも、-LastTranslated 未指定なら実行時に入力を求めます。
  リポジトリのルートを指定した場合は s\article を自動採用します。
.EXAMPLE
  # モードもパスも対話で入力
  .\Run-FileComparison.ps1
.EXAMPLE
  # モードだけ先に指定（パスは対話入力）
  .\Run-FileComparison.ps1 -Mode Project
.EXAMPLE
  # すべて引数で指定
  .\Run-FileComparison.ps1 -Mode Fullset -LastTranslated "C:\...\domo-documentation-hub-0608"
.EXAMPLE
  # 翻訳対象の文字列だけを変更とみなす
  .\Run-FileComparison.ps1 -Mode Project -LastTranslated "C:\...\s\article" -TranslatableOnly
#>
param(
    [ValidateSet("Fullset", "Project")]
    [string]$Mode,
    [string]$LastTranslated,
    [string]$Current,
    [string]$Results,
    [switch]$TranslatableOnly
)

$py = "C:\Program Files\Python311\python.exe"
$script = Join-Path $PSScriptRoot "file_compare_fullset.py"

if (-not (Test-Path $py))     { Write-Error "Python が見つかりません: $py"; exit 1 }
if (-not (Test-Path $script)) { Write-Error "スクリプトが見つかりません: $script"; exit 1 }

# --- モード選択（-Mode 未指定なら対話で質問） ---
if (-not $Mode) {
    Write-Host ""
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "   File Comparison — 比較モードを選択してください" -ForegroundColor Cyan
    Write-Host "==================================================" -ForegroundColor Cyan
    Write-Host "  [1] Fullset  (全ファイル比較)"
    Write-Host "  [2] Project  (プロジェクト比較)"
    Write-Host "--------------------------------------------------"
    $chosen = $null
    do {
        $sel = (Read-Host "番号を入力してください (1/2)").Trim()
        switch ($sel) {
            "1" { $chosen = "Fullset" }
            "2" { $chosen = "Project" }
            default { Write-Host "1 か 2 を入力してください。" -ForegroundColor Yellow }
        }
    } while (-not $chosen)
    $Mode = $chosen
    Write-Host "選択: $Mode" -ForegroundColor Green
}

# --- Last translated フォルダー ---
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

Write-Host "$Mode 比較を開始します..." -ForegroundColor Cyan
& $py @cmdArgs
