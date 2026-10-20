# 作業ログ 2026-10-20（その4） — Kotonoha beta3 JSON: チップUI・UI改修・MT注入

## 概要
Domoアプリ JSON 翻訳対応の続き。バックエンド（その3）に続き、**TEP編集画面のインライン保護タグ（チップ）UI**・**全幅レスポンシブ/列幅調整**・**MT訳の注入**まで実施。全変更は**両コピー（Apps-local／GitHub-production）に同期**（ハッシュ一致確認）。

## 実装（`TM-Match-Explorer-demo.html`）
- **インライン保護タグ＝チップ**: `{n}` を**小さなbox＋番号のみ**で表示、**元タグはマウスオーバーのツールチップ**（`title`）。原文・TM訳・訳文の全列でチップ表示（`withChips`）。
  - 訳欄は `textarea`→**`contenteditable` div** に変更。チップは `contenteditable=false`＝**編集不可・ドラッグ移動/並べ替え可・Backspaceで1個削除**。
  - 編集モード時、訳欄上に**タグ挿入パレット**（そのセグメントの全タグを番号チップで表示→クリックでカーソル位置に挿入）。
  - 保存は `serializeJa`（childNodes走査→テキスト＋`{n}`）で `edits[i]` に格納。XLIFF/`jaValue`/確定は従来踏襲。SEG各行に `tags{n:元タグ}` を添付（`tm_match_analysis` と `json_io.extract` で付与）。
- **全幅レスポンシブ**: `.wrap{max-width:none}`（上限撤廃・左右余白clamp）。
- **列幅**: セグメント表を `table-layout:fixed`＋colgroup で `# 42px / Match 92px / English 27% / TM 19% / Japanese 46% / 確定 54px`（**Japanese を最大**）。
- （前段）翻訳/サマリーのタブ化・固定3ペイン(履歴/用語)・ヘッダ撤去しタブ行にテーマ/ファイル名、は維持。

## MT注入（ご依頼「Pre-translationにMT訳表示」）
- 実 University＋Product を適用して生成 → **TM流し込み 222 / MT対象 58 / 総280**。
- MT対象58行を Claude が翻訳（`{n}`タグ位置込み・UI要素/タイル/ボタン名は英語維持・説明文を日本語化）→ `mt-done.jsonl` → `inject_mt.py --html --mt` で注入。**58 filled・空0・文字化けなし**。→ 280行すべてに訳。

## 生成物の永続保存（★明日の再開用）
`…\ED2710-20-MH-App-September 2026 Release Update Content-JA\_kotonoha\`:
- `Creating DataFlows in Magic ETL.TEP.html`（MT注入済みTEP・チップUI）
- `….TEP.html.uidmap.json`（復元用 index→uid・元JSONの絶対パス入り）
- `….mt-done.jsonl` / `….mt-todo.json`
（元JSON: `…\2_For review\Creating DataFlows in Magic ETL.json`）

## 明日の再開ポイント（NEXT）
1. `_kotonoha\…TEP.html` をブラウザで開き **TEP（確認・編集・確定）** → XLIFF 書き出し。
   - MT訳の方針調整（UIラベルを日本語化する等）があれば先に相談。
2. 確定XLIFFを復元:
   `python projects.py reinsert-json --xliff <確定.xliff> --uidmap "_kotonoha\…TEP.html.uidmap.json" --out "…\2_For review\Creating DataFlows in Magic ETL_JA.json"`
   → 翻訳済みJSON（タグ・構造・name・URL復元）。
3. （任意）この JSON 対応を launcher/serve の導線に載せる・マニュアル反映。実運用TM書き戻しで Master を育てる。

## 状態
- 全 `.py`(json_io/tm_match_analysis/projects) py_compile OK・両コピー同期。`demo.html` 両コピー同期。
- TEMPの作業コピーは消える可能性あり → 上記 `_kotonoha\` が正。
