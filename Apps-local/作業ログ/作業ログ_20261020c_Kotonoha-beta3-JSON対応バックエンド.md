# 作業ログ 2026-10-20（その3） — Kotonoha beta3 Domoアプリ JSON 翻訳対応（バックエンド）

## 概要
Domoアプリ コンテンツ JSON（`…\ED2710-20-…-JA\2_For review\Creating DataFlows in Magic ETL.json`）を Kotonoha で翻訳するため、**JSON の抽出→pre-translation→（TEP）→JSON復元** の往復を恒久対応として実装（plan: `smooth-dreaming-pnueli.md` 承認済み）。本ログは**バックエンド（抽出・生成・復元）**まで。TEPのインライン保護タグ（チップUI）は次段階。

## 実装
### 新規 `json_io.py`
- 翻訳対象＝表示テキスト全部（app_name / 各ページ displayName / fields.title,description,instructions / pinpoints[].header,copy / tasks[].label,description,copy / videos[].subtext / modalVideos テキスト）。`pages[].name`・真偽値・URL・属性値は対象外。
- `HTMLParser` ベースの `split_field`：各フィールドHTMLを**ブロック(<p>/<li>/<h*>等)単位**に分解、**1ブロック=1セグメント**（文分割なし）。インラインタグ（<strong>/<span>/<a>/<br>等）は**番号プレースホルダ `{n}`** に退避（`tags{n:元タグ}` は `get_starttag_text()` で属性ごと保持）。
- `extract(path)` → `[{uid,text}]`（uid=`<fieldpath>#<slot>` 例 `pages[7].fields.tasks[0].copy#3`）。`apply(path,out,trans)` は元JSONを**再抽出**して構造/タグを得て `{n}`→元タグ復元・ブロック再構築・翻訳済みJSON書き出し（compact・ensure_ascii=False）。未訳uidは原文維持、name/属性/真偽値は無改変。

### `tm_match_analysis.py`
- ソースが `.json` のとき `read_segments` の代わりに `json_io.extract` を使用（順序保持）。`<out>.uidmap.json`（{json, uids[]}）を出力。filepill=app_name。**SEG index = 抽出順 = XLIFF id−1**。

### `projects.py`
- 新サブコマンド **`reinsert-json`**（`--xliff --uidmap [--json] [--out] [--confirmed-only]`）：XLIFF の trans-unit id(=index+1)→uid(uidmap)→`json_io.apply` で翻訳済みJSON出力。関数 `reinsert_json()`。
- `.json` は file ソースとして `run_project`→`expand_sources`（file種は拡張子不問）経由でそのまま処理される（run_project 無改修）。

## 検証（実ファイル・小TMXで高速）
- `json_io` 往復（擬似訳でプレースホルダ保持）: 280セグメント抽出/復元、有効JSON・pages同数・app_name訳・`name`据置・`<strong>`/`<li>`/`<a href>` 復元・リスト保持。
- 生成: 実JSON→TEP HTML（SEG 280・うち108にプレースホルダ）＋uidmap（uids 280・json参照）。
- 復元(実コード): SEGから擬似確定XLIFF(id=index+1)→`reinsert-json`→翻訳済みJSON（適用280・タグ復元・構造保持）。
- 全3 `.py` py_compile OK。**両コピー（Apps-local／GitHub-production）に同期**（ハッシュ一致）。実ファイルは直接上書きせず `_JA.json` 別出力。

## 残（次段階）
- **TEP編集画面のインライン保護タグ（プレースアブル）UI**：`{n}` をロックされたチップ（編集不可・移動/並べ替え可）で表示する `TM-Match-Explorer-demo.html` の拡張（本機能の最大パート）。現状は `{n}` が素のテキストとして見える。
- 選択肢: Phase1＝`{n}` をテキストトークンのまま textarea 運用で翻訳を先に回す（移動可だが編集可）／Phase2＝ロックチップ（完全形）。
- 実運用TM（University 414MB 等）での実翻訳、実機ブラウザ確認、マニュアル反映。
