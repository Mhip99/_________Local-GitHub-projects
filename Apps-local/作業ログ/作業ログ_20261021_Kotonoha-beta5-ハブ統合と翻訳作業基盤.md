# 作業ログ 2026-10-21 — Kotonoha beta5：ハブ統合・翻訳作業基盤

## 概要
beta3 を **beta5**（縁起で beta4 は飛ばし）として起こし、ダッシュボードを全ツールのUIハブに統合。さらに翻訳作業（TEP）を実運用できる基盤（自動保存・既定表示・切替確認・メインTM新規作成）を整備。全変更は `Apps-local`（正本）↔ `CAT tool\CAT`（本番コピー）に同期。Git コミット済み（最新 **32a5e97**、未 push）。

## 本日の実装（Git履歴）
- **ad69565**: beta5化（beta3表記更新）、JSON翻訳MTを **Domo TM準拠に再ローカライズ**→TEP再注入、編集ペイン右クリック3機能（元に戻す=undo/英語のまま/履歴をコピー）、サマリーに **ファイル/TM/プロジェクト情報ペイン**（保存場所を開く）、`tm_match_analysis` に META 自動注入（`--project-name/--project-detail`）。
- **41bc1d7**: ワンクリック起動 **`起動_Kotonoha-ハブ.bat`**（serve＋ブラウザ自動）。ハブに **File Comparison / JA Version Check** を統合（`/api/filecompare`・`/api/versioncheck`）。
- **6d2d9ab**: ダッシュボードを **2親タブ**（プロジェクト / TM Match Explorer）に統合。TEP は iframe 表示、`/explorer` 既定、記事「開く」は同画面内表示。見出し・説明文をプロジェクトタブ内へ移動。
- **32a5e97**: 作成ダイアログ **メインTM「＋新規作成」**（空TMX生成 `/api/new-tmx`）、「作成のみ」→「保存」。TEP **「途中保存」＋Ctrl+S＋自動保存**（デバウンス、`/api/save-edits`・`/api/load-edits`、`_wip/` サイドカー、次回開くと自動復元）。TM Match Explorer タブは**直近に開いた記事を既定表示**、別記事を開く際は**確認ダイアログ**。`.gitignore` に `_wip/`・`Kotonoha-out/`。

## 同期・保存
- 同期ルール: `Apps-local` が正本 → `robocopy ... /E /XD __pycache__` で `CAT tool\CAT` へ（削除なし）。Stopフックも設定済み（`.claude\settings.local.json`）。
- 実データ（TEPの編集・確定）は `_wip/<記事名>.json`（サーバー保存）＋ localStorage。CATにも同期＝両所から復元可。

## 明日の再開ポイント（NEXT）
1. **`Apps-local\Kotonoha-beta5\起動_Kotonoha-ハブ.bat` をダブルクリック** → ブラウザにハブ（http://127.0.0.1:8765/）。F5で最新。
2. 「プロジェクト」タブ → 記事行 **「Creating DataFlows in Magic ETL」**（proj 定義 `proj-20261021-163537`／280セグメント・MT対象58）の「**開く**」→ TM Match Explorer タブで翻訳。編集は**自動保存**。
3. **MT対象58行**を埋める: `Kotonoha-out\ED2710…\combined.mt-todo.json`（または `….mt-todo.json`）を AI 翻訳 → 「**ツール ▾ → MT を HTML に注入**」。
4. 確定 → **XLIFF 書き出し** → JSONソースなので **`projects.py reinsert-json`** で元JSONへ復元。
5. テスト継続。必要なら `git push`（現在ローカルコミットのみ）。

## 状態
- 全 `.py` py_compile OK、`demo.html`/`projects.py` のJS構文OK。ハブ稼働確認済み（セッション終了時にサーバー停止）。
- 関連: `Apps-local\作業ログ\作業ログ_20261020d_…`（JSON対応の前段）。
