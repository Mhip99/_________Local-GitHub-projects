# 作業ログ 2026-10-07 — Kotonoha beta3（変更履歴/Rev・ページ番号・プロジェクト機能・作成ウィザード）

## 概要
Kotonoha beta3（`CAT tool\CAT\Kotonoha-beta3\`）に、マニュアルの体裁整備（変更履歴の分割・Rev 付番・ページ番号）と、**過去のプロジェクト機能**（台帳＋ブラウザ・ダッシュボード）、**プロジェクト作成ウィザード**を追加。マニュアルを **Rev. 2.00** に更新（旧 Rev 1.00 は保存）。

> 大きな機能追加のため、Rev 付番ルール（整数部＝大きな変更）に従い `1.00 → 2.00`。

---

## 1. マニュアル体裁（Rev 1.00 系）
- **変更履歴を 1.1 / 1.2 に分割**：
  - **1.1 仕様変更履歴**（ツール仕様・版別/日付、記法は従来どおり）
  - **1.2 ドキュメント変更履歴**（本マニュアルの変更を 1〜2 行で簡潔に、1.1 へ内部リンク `#spec-history`）
  - リーダーを `commonmark_x+attributes` に変更（CJK 太字＋見出し `{#id}` を両立。`gfm` は header_attributes 非対応、`markdown` は CJK 隣接の `**強調**` を取りこぼすため）。
- **Rev. no. を表紙とファイル名に付与**（表紙＝YAML `author`、ファイル名＝`_Rev1.00`）。**付番ルールを明文化**：`<整数部>.<小数部2桁>`、大きな変更＝整数部+1、小さな変更＝小数部+0.01。
- **ページ番号**（フッター中央・PAGE フィールド）を参照 docx に埋め込み、`updateFields` で Word 起動時に自動更新。

## 2. 過去のプロジェクト機能（[P]）
- **`projects.py`**（台帳 `_projects.json` 管理）：`add`/`add-batch`（[1]/[2] 実行時に自動登録）・`list`/`get`・`set-status`・`set-memo`/`set-due`・`set-outdir`/`set-assignee`・`remove`（ファイル保持/削除）・`srcs`/`subs`・`undo-source`/`undo-sub-tm`・`dashboard`。
- **ブラウザ別タブの一覧ダッシュボード `_projects.html`**（TEP 作業とは別タブ）：
  - 各行「開く」で成果物 HTML を別タブ表示＝作業再開（localStorage の編集・確定を継承）。
  - 状態（作業中/レビュー中/完了・手動切替）、メモ・期日、検索・状態フィルタ・「完了を隠す」。
  - **表 UI**：列幅リサイズ（ヘッダー右端ドラッグ）／列の表示・非表示（`列 ▾`）／列のドラッグ並べ替え／`固定`（編集ロック）／`既定に戻す`／右端固定の独立「開く」ボタン（見切れない）／ウィンドウ幅追従／行・セル罫線。設定は localStorage 保存。
- ランチャー **[P]**：ダッシュボードを別タブで開き、コンソールで状態切替/メモ/期日/削除/新規作成(N)/再表示。

## 3. プロジェクト作成ウィザード（[C]）
一連の流れ：**プロジェクト名 → ソース追加（ファイル/フォルダー・複数・階層維持）→ メイン TM／サブ TM（複数・新規作成＝空 TMX 可）→ 追加情報（出力先/担当者/期日/メモ）→ 定義保存**。
- 各ステップで現在の内容を再表示、`U=直前を取消`、既定 TM を初期表示（Enter 採用）、新規項目では空の「現在:」を非表示。
- ※ **定義の作成・保存まで**実装（保存した定義での解析＋Pre-translation 実行は次ステップ）。

## 4. ランチャー共通の改善（本日）
- 全操作で**入力の実在チェック**、未検出時 `再入力(R) / キャンセル(C)`、**キャンセルで一つ前の入力に戻る**（最初の入力はメニューへ）。
- 遅延展開下の `!` によるメッセージ欠落（`[!]`）を `※` に置換して修正。

---

## 5. 成果物（Kotonoha-beta3）
| ファイル | 内容 |
|---|---|
| `TM-Match-Explorer.bat` | ランチャー（[C] 作成・[P] 一覧・入力検証/キャンセル戻り・CRLF） |
| `projects.py` | プロジェクト台帳＋ダッシュボード生成（新規） |
| `_projects.json` / `_projects.html` | 台帳 / 一覧ダッシュボード（自動生成） |
| `Kotonoha-beta3-マニュアル_Rev2.00.md` / `.docx` | **最新マニュアル（Rev 2.00）** |
| `Kotonoha-beta3-マニュアル_Rev1.00.md` / `.docx` | 旧版（保存） |
| `_build-manual-docx.bat` | docx 再生成（`commonmark_x+attributes`、入出力は _Rev2.00） |
| `tm_index.py` / `tm_match_analysis.py` / `inject_mt.py` / `tm_writeback.py` / `ui_glossary.py` / `TM-Match-Explorer-demo.html` / `_cover-pagebreak.openxml` / `pandoc-reference.docx` | 既存（変更なし） |

## 6. 検証
- `projects.py` 全コマンドを直接実行で確認（create/add-source[file,dir]/undo/main・sub TM/new-tm/outdir/assignee/due/memo/show/srcs/subs/dashboard）。
- ランチャー：CRLF・構文パース OK（menu→Q, exit 0）、[C]/[P] 表示、[1] 実行→自動登録。
- マニュアル：Rev 2.00 の表紙・§4a・構成ファイル・1.1/1.2 変更履歴を docx で反映確認。pandoc exit 0。
- **注意（テスト制約）**：Windows の `cmd` は `choice` がリダイレクト入力だと後続入力を消費するため、`choice` を含むウィザードの通し自動テストは不可。実機（キーボード操作）では正常。[C] は実機 `TM-Match-Explorer.bat` で確認する運用。

## 7. 残タスク（次回）
- 保存したプロジェクト定義を使った **解析＋Pre-translation の実行連携**（複数ソース＋フォルダー階層維持の出力、メイン＋複数サブ TM での索引、combined.mt-todo 生成）。
- 完了後、[1]/[2] を [C]/[P] のプロジェクトフローへ統合（UI 統一）。
- 必要に応じ Rev 2.00 docx の体裁最終確認（表紙を番号なしにする等の調整は要望次第）。
