# 作業ログ 2026-10-14 — Kotonoha beta3（全機能をブラウザGUI＝サーバーモードで実行可能に）

## 概要
サーバーモード（`projects.py serve` → ブラウザ）で、これまでランチャー `TM-Match-Explorer.bat` のコンソールメニューからしか実行できなかった機能を**ブラウザGUIから実行**できるようにした。計画は承認済み（plan: `smooth-dreaming-pnueli.md`）。実装前に Explore 3本で現状調査（補助スクリプトの入出力・serve/dashboard の拡張ポイント）。

対象（今回GUI化）: 状態 / メモ / 期日 / 削除、MT注入（単一・一括）、索引キャッシュ事前作成、TM書き戻し（dry-run＋自動バックアップ）、UI Glossary。
**次段階（今回しない）**: 翻訳履歴ペイン＋TMへの全TU蓄積（現行は上書き型。ユーザー仕様＝上書き・削除せず更新日時付きで蓄積）。暫定として書き戻し本実行前の TMX 自動バックアップで橋渡し。

## 方針の確定（ユーザー回答）
- 重い処理（索引ビルド等・数分）は**同期**（既存 `/api/run` 流儀。「実行中…」表示＋タブを閉じない案内）。
- TM書き戻しは **dry-run必須フロー＋本実行直前に TMX 日付きバックアップ**。
- 履歴ペイン/蓄積は次段階。

## 実装（`projects.py` 1ファイル・既存パターン踏襲）
> 設計変更: 補助スクリプトは `main()` 化せず、**`export_project` が `doc_export.py` を subprocess 起動するのと同じ方式**で呼ぶ（スクリプトは非対話CLIとして完成済み・import用リファクタの risk 回避）。例外は索引のみ（下記）。

### サーバー側（新 API ルート・`do_POST`）
- `/api/set-status` `/api/set-memo` `/api/set-due` … `update_field(projects, store, pid, field, value)`（**pidベース**・`updated` も更新）
- `/api/remove` … `remove_project(...)`（`delete_file` で成果物HTML＋`.mt-todo.json` も物理削除）
- `/api/inject` … `inject_mt_run(mode single|batch, ...)` → `inject_mt.py`
- `/api/prebuild` … `prebuild_index(...)`。**索引だけは subprocess ではなく `tm_index.load_or_build` を import 経由で呼ぶ**（`tm_index.py` を `__main__` 実行すると `Index` が pickle できずキャッシュ保存失敗、という既知事象を回避。`tm_match_analysis` と同じ正常保存経路）。※ランチャー[5]は従来どおり `__main__` 実行なので同事象が残る可能性＝別途要確認。
- `/api/writeback` … `writeback_run(..., dry_run, backup=True)` → `tm_writeback.py`。**本実行(dry_run=False)の直前に** `master`/`project_tmx` を `<base>.bak_YYYYMMDD-HHMMSS<ext>` へ `shutil.copy2` でバックアップ（失敗時は中止）。
- `/api/glossary` … `glossary_run(...)` → `ui_glossary.py`。`<out>.csv`/`.json`。
- `/api/reveal` … `os.startfile(folder)`（出力フォルダをエクスプローラーで開く）。
- 共用 `_run_script(cmd, capture)`（subprocess＋stdout捕捉）。各関数は結果 dict（`ok`/`error`/`log`/件数など）を返す。

### ファイル選択の種別拡張
- `TK_PICK`（ネイティブ）と `list_dir`（フォールバック browser）に **xliff / html / json** の拡張子フィルタを追加（従来は tmx/source/dir のみ）。

### 行データ
- `build_rows` の各行に `id` を追加（成果物行も状態/メモ/期日/削除できるように。従来 `pid` は定義行のみ）。

### クライアント（`dashboard_html` 内 JS・served 時のみ）
- 操作列に「**編集**」ボタン（全行）。`openEdit(p)`＝状態セレクト＋メモ＋期日＋**2段階確認の削除**＋保存（`set-status`/`set-memo`/`set-due` を並行送信）。
- ツールバーに「**ツール ▾**」メニュー（served時のみ表示）→ `openInject` / `openPrebuild` / `openWriteback` / `openGlossary`。
- 書き戻しダイアログは **dry-run→プレビュー枠→本実行**（本実行はdry-run後に有効化）、結果にバックアップ件数表示。
- Glossary 完了時は結果ログ＋「出力フォルダを開く」（`/api/reveal`）。
- 汎用部品: `modalShell` / `textField` / `pathFieldK(kind)` / `listFieldK(kind)` / `busy` / `showLog`（`openCreate` の骨格を一般化）。操作列幅 served 時 240px に拡張、CSS（`.toolspanel`/`.edit`/`.pre`/`select`/`textarea`）追加。説明文（`.sub`）更新。
- 静的 file:// 版は従来どおり（編集/ツールは出さない。`if(KT.served)` でのみ有効化）。

## 検証（E2E・隔離）
- 隔離 `--store`＋合成データ（プロジェクト／HTML+mt-done／小TMX／XLIFF+scratch master／mdx）でサーバー起動→全新ルートをHTTPで実行:
  - set-status/memo/due → `/api/projects` に反映、remove → 0件。
  - inject single → filled 2。
  - prebuild → **キャッシュ `idx_*.pkl` が保存される**ことを確認（import版修正後）。
  - writeback dry-run（added 1）→ 本実行（`ok`＋`scratch-master.bak_*.tmx` 生成）。
  - glossary → `.csv`/`.json` 生成。
  - 無トークン 403。
- `py_compile` OK。served版HTMLに新UI要素（toolswrap/openEdit/各API/`class="edit"` 等）が含まれ、プレースホルダ置換済みを確認。
- 実台帳 `_projects.json`（3件）無傷。静的 `_projects.html` 再生成（47,900 bytes）。
- テスト一時フォルダは削除。※ `__testdata-1014\`（手動テスト用データ）は残置。

## 残タスク
- **実機ブラウザ確認**（`[D]` サーバーモードで各ダイアログの描画・ネイティブ選択・結果トースト・`refresh` 反映）。テストプラン `テストプラン_beta3_20261014.md` に追補予定。
- **マニュアル Rev 3.00**（全機能GUI化は大機能追加＝整数部+1候補。付番は要相談）。bat 案内文・manual 反映、pandoc で docx 再生成。
- （次段階）翻訳履歴ペイン＋TM蓄積型への変更（データモデル設計）。
- （要確認）ランチャー[5]索引事前作成の `__main__` pickle 事象（GUI版は回避済み）。
- 編集ダイアログの削除は現状「ファイルは残す」固定（安全側）。ファイルも消す選択肢の要否は要相談。
