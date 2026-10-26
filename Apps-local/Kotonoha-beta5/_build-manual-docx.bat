@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem マニュアル docx を .md から再生成 (表紙=YAMLメタデータ, 目次=--toc, 表紙後に改ページ)
rem Rev を上げるとき: _Rev2.00.md を _Rev1.1.md 等にコピー→メタデータ author/date を更新→
rem   下の pandoc 行の入出力ファイル名を新 Rev に変更 (旧 Rev ファイルは削除せず残す)。
where pandoc >nul 2>nul || (echo [ERROR] pandoc が見つかりません & pause & exit /b 1)
pandoc "Kotonoha-beta5-マニュアル_Rev4.00.md" -o "Kotonoha-beta5-マニュアル_Rev4.00.docx" --from "commonmark_x+attributes" --reference-doc "pandoc-reference.docx" --toc --toc-depth=3 --include-before-body "_cover-pagebreak.openxml"
if errorlevel 1 (echo [ERROR] pandoc 失敗 & pause & exit /b 1)
echo 完了: Kotonoha-beta5-マニュアル_Rev4.00.docx を再生成しました。
pause