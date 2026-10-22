# 作業ログ 2026-10-22 — Kotonoha beta5：出力多形式・用語/UI刷新・記事の独立プロジェクト化

## 概要
ハブ(ダッシュボード)の UX/用語/タブを刷新し、翻訳作業を実運用できる形に。全変更は `Apps-local`(正本) ↔ `CAT tool\CAT` に同期。Git は本日 `83143b3`→`68eaa96`。未 push。

## 本日の実装（Git履歴）
- **83143b3**: 「出力」を **JSON/DOCX/XLSX 対応**（doc_io に json_io/python-docx/openpyxl ハンドラ）。用語「MT注入」→「**MTを反映**」・半角英数前後スペース除去（UI＋マニュアル）。親タブを**プロジェクト名タブ**に刷新（複数・折返し2行・×閉じ・0件時のみ TM Match Explorer）。実行/開くで生成記事を**自動タブ表示**、タブ名＝プロジェクト名。`/article` を開く時に**最新テンプレートへ貼り替え配信**（SEG流用）＝古い記事も常に最新UI。サマリー**2カラム**（左上=ファイル/TM/プロジェクト情報→区分内訳、右=数値）。
- **68eaa96**: 記事行を **[実行/出力/編集] に統一**（各記事を自分のソース+TMで実行/出力できる**独立プロジェクト化**。upsert がレシピ=sources/main_tm/sub_tms/product_tm/out_dir を記録、run_project/export_project を「実行可能(ソース+メインTM)」判定に緩和。開くは実行に統合）。**実行(再生成)しても保存済みMT訳を自動再反映**＝データ損失防止。`inject_mt` の SEG 検出を META/BANDS どちらでも一致に修正（反映不具合解消）。古いテスト行(Changes in Account/Test 001/DomoStats)を台帳から削除。

## 現在の状態（台帳）
- **ED2710-20-MH-App-September 2026 Release Update Content-JA**（定義）→ 実行/出力/編集
- **Creating DataFlows in Magic ETL**（記事・280セグメント／TM222・MT58反映済み）→ 実行/出力/編集

## MT対象58行
TM準拠訳で反映済み（mt-done＝`Apps-local\Kotonoha-out\ED2710…\Creating DataFlows in Magic ETL.html.mt-done.jsonl`）。実行で再生成されても自動再反映される。

## 明日の再開ポイント（NEXT）
1. `Apps-local\Kotonoha-beta5\起動_Kotonoha-ハブ.bat` をダブルクリック → ハブ(http://127.0.0.1:8765/)。F5で最新。
2. 記事「Creating DataFlows in Magic ETL」の「**実行**」で開く（＝再生成＋MT自動再反映＋プロジェクト名タブ表示）。※単に見るだけでも実行＝再生成になる点に注意（MTは自動保持）。
3. 翻訳レビュー・確定（**自動保存**）→「**出力**」でJSON出力、または TEP「XLIFF書き出し」→ `projects.py reinsert-json` でJSON復元。
4. テスト継続。必要なら `git push`（現在ローカルのみ）。

## 状態
- 全 .py py_compile OK。inject_mt/doc_io 動作確認済み。ハブ稼働確認済み（セッション終了時にサーバー停止）。
- 関連: `作業ログ_20261021_…`（ハブ統合・翻訳基盤）。
