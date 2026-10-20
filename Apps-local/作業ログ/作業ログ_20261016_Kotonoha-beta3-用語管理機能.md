# 作業ログ 2026-10-16 — Kotonoha beta3 用語管理（termbase）機能

## 概要
Rev 3.00 で領域だけ確保していた「用語ペイン」の中身＝**用語管理機能**を実装。計画承認済み（plan: `smooth-dreaming-pnueli.md`）。実装前に Explore 2本で土台（ストア/サーバー/ダッシュボード/配信）と抽出の再利用点を調査。

ユーザー要件（確定）:
- 翻訳中ドキュメント／既訳から**ユーザー指定の用語**を抽出・登録。項目＝**ソース・ターゲット・用例・ノート・日付・ドキュメント名・プロジェクト名**。
- **全プロジェクト共通の単一ファイル／保存形式 TSV**（エクスポートなしでローカル参照可）。
- **TSV／CSV／Xlsx を選択してエクスポート**。
- **用語管理タブ**で CRUD。**編集画面でもライブ登録**（＝編集画面のサーバー配信化）。

## 実装（5段階・各段で py_compile＋HTTP 検証）

### 1. TSV 用語ストア＋用語API＋最小XLSXライタ（`projects.py`）
- 既定 `Live_TM\_terms.tsv`（`--term-store` で上書き）。列: `id source target example note doc project created updated`。`load_terms`/`save_terms`（標準 `csv`・`delimiter="\t"`・`utf-8-sig`＝用例/ノートの改行も安全に往復）／`make_term_id`／`term_save`/`term_delete`/`terms_for_segment`（原文への部分一致）。
- エクスポート `export_terms`（tsv/csv＝BOM付・標準ライブラリ、**xlsx＝依存なしの最小 OOXML ライタ `_write_xlsx`**・inlineStrで日本語）。
- 新API（serve・既存定型）: `GET /api/terms`（`?seg=` で関連用語）・`POST /api/term-save`/`term-delete`/`term-export`/`term-extract`。`TERMSTORE` 変数、`--term-store` 引数。

### 2. ダッシュボードに「用語管理タブ」（`dashboard_html`）
- タブUI新設（プロジェクト／用語管理・`served` 時のみ `#tabs` 表示）。`#view-projects`/`#view-terms` を切替（`switchView`）。
- 用語テーブル `#ttable`（source/target/用例/note/doc/project/更新/操作）。検索・`openTermEdit`（追加/編集・既存モーダル基盤流用）・2段階確認の削除・`openTermExtract`（ソース/HTML/XLIFF をpick→`/api/term-extract`＝ui_glossary候補→チェックで一括登録）・エクスポート（TSV/CSV/Xlsx）。

### 3. 編集画面の配信化（`projects.py` serve）
- `GET /article?id=<台帳行id>` を新設：登録済み成果物HTMLを読み、先頭に `<script>window.__KT={served,token,doc,project}</script>` を注入して配信（**登録済みhtmlに限定＝トラバーサル防止・未登録は404**）。
- `build_rows(projects, served=False)` 追加：served 時は `uri` を `/article?id=…`（http・同一オリジン）に。`dashboard_html`／`/api/projects` が served を渡す。
- **副次修正（重要）**: 成果物エントリに `id` が無かった問題を解消。`upsert` で新規成果物に `id` 付与、`row_id(p)`（無idは html から派生 `art-<md5>`）＋`find_by_row_id` を新設し、`/article`・`update_field`・`remove_project` を row_id 解決に（＝成果物行の編集/削除/配信が実IDなしでも機能）。

### 4. 編集画面の用語ペイン＋ライブ登録（`TM-Match-Explorer-demo.html`）
- 右下 `termpane` を実装（履歴ペインの実装を踏襲）。行クリックで `renderTerms(i)`：served は `GET /api/terms?seg=<原文>` で関連用語、非served は `SEG[i].glossary` を読み取り表示。
- **ライブ登録（served）**: 原文セルでテキスト選択→登録エリア表示（ソース=選択語、ターゲット=その行の訳を既定、用例=原文、doc/project=`window.__KT`）→`POST /api/term-save`→ペイン再取得。`window.__KT` 不在（file://）は読み取り専用にフォールバック。

### 5. 全SEG行に `glossary` 付与（`tm_match_analysis.py`）
- 従来 MT 行のみだった `glossary_hits(sn)` を**全セグメント行**に付与（非served 用語ペインの関連用語表示用）。pct/st/band は無改修。

## 検証（隔離・HTTP。実 `_terms.tsv` は作らない）
- TSV 往復（改行/タブ含む）・`make_term_id` 重複回避・ローカルでTSV参照可。
- API: term-save（追加/更新）・terms（全件/`?seg=`）・term-delete・term-export（tsv/csv/**xlsx**生成, Excel可）・term-extract（mdxの `**bold**` から候補）。無トークン403。
- 配信: `/article?id` が `__KT`(served/token/doc/project) 注入HTMLを返す／未登録404。`build_rows(served)` の uri＝`/article?id=…`。成果物行の set-status が row_id 経由で成功。
- 生成HTMLに用語管理UI（tabs/view-terms/ttable/openTermEdit/openTermExtract/switchView）・編集画面に用語ペインJS（renderTerms/termadd）を確認。全 `.py` py_compile OK。

## 残・注記
- **実機ブラウザ確認が必要**（タブ切替・用語CRUD・抽出登録・エクスポート・編集画面の `/article` 経由での用語ペイン表示＋選択→ライブ登録）。
- 非served フォールバックの `SEG.glossary` は `glossary_hits` のトークン一致で、語に句読点隣接だと拾えないことがある（フォールバック専用・本命のserved は部分一致で堅牢）。
- 編集画面を**サーバー配信（[D]→一覧の「開く」）経由**で開くとライブ連動。`file://` 直開きは読み取りのみ。
- マニュアルは別途 Rev 更新（用語管理・配信化・タブ）。
