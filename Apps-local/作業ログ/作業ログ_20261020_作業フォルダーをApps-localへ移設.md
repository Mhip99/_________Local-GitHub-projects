# 作業ログ 2026-10-20 — 作業フォルダーを Apps-local へ移設

## 概要
フォルダー構造とファイルが増え煩雑になったため、作業フォルダーを **`C:\Users\Masaaki.Hori\OneDrive - Domo Inc\_________Local-GitHub-projects\Apps-local`** へ**コピー**で移設（元 `________GitHub-production` も残す＝可逆）。

## コピー内容
- **`Apps-local\Kotonoha-beta3\`**（17ファイル）: 実行に必要な最新版＋Rev3.00マニュアル＋台帳。
  - コード: projects.py / tm_index.py / tm_match_analysis.py / inject_mt.py / tm_writeback.py / ui_glossary.py / doc_io.py / doc_export.py / TM-Match-Explorer.bat
  - テンプレート: TM-Match-Explorer-demo.html
  - マニュアル(最新): Kotonoha-beta3-マニュアル_Rev3.00.md / .docx ＋ ビルド補助 pandoc-reference.docx / _build-manual-docx.bat / _cover-pagebreak.openxml
  - 台帳: _projects.json（引継）＋ _projects.html
  - 除外: 旧Rev1.00/2.00マニュアル・テストプラン・__pycache__・_pt(scratch)・TM-Match-Explorer.bat.bak
- **`Apps-local\File comparison\`**: 旧版 `EN_comp\Alpha` 以外すべて。
  - `日本語版チェック指示書.txt`／`EN_comp\Beta1`（File Comparison 最新: Run-FileComparison.ps1 / .bat / マニュアル）／`JA_comp`（JA Version Check: ja_version_check.py / Run-JAVersionCheck.ps1 / tm_ja_en.py / .bat / マニュアル）／`__Results`（出力xlsx）。
- **`Apps-local\作業ログ\`**: 旧 `________GitHub-production\作業ログ` の全18件をコピー。以後の作業ログはここへ。

## 運用ルール（ユーザー指定）
- **以後の正＝Apps-local**。ただし「**両方を同期**」：ツール編集時は元 `________GitHub-production\CAT tool\CAT\Kotonoha-beta3` にも同じ変更を反映。
- **TMデータは移さない**：`________GitHub-production\TM manaegment\TM\___Working\`（XTM・索引キャッシュ・Live_TM・用語集 _terms.tsv）はそのまま。ツールの .bat 既定パス／tm_writeback の TM_ROOT／用語集既定は従来の絶対パスを指す＝移設後も同じTMを読み書き（破損なし）。

## 検証
- コピー先 Apps-local\Kotonoha-beta3 で全8 .py を `py_compile` → OK。
- .bat 既定パス（XTM/CACHE/LIVETM）が従来の TM management を指すことを確認。
- File comparison は `EN_comp\Alpha`（旧版）が除外されていることを確認。
- コピー時に紛れた __pycache__ は削除（File comparison\EN_comp\Beta1 の1つは OneDrive ロックで残存・無害）。

## メモリ更新
- `work-log-location`：保存先を Apps-local\作業ログ に更新。
- `apps-local-relocation`（新規）：移設の全容・運用ルールを記録。
- MEMORY.md 索引を更新。

## 残タスク
- 実機ブラウザ確認（用語管理）。
- マニュアル更新（用語管理・配信化・タブ反映）。両方を同期で反映。
