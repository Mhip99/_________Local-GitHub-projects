# 作業ログ 2026-11-17 — Kotonoha beta6：TM タブ表記の改善（読み取り専用→一括更新・役割ラベル簡素化）

## 概要
ED2710 の TEP 再開にあたり、ユーザーから TM タブ（`view-tm`）の表記がわかりにくいとの指摘。2点を修正した。全変更は `Apps-local`（正本）→ `________GitHub-production\CAT tool\CAT\Kotonoha-beta6`（本番コピー）へ同期済み。配信元は `projects.py` の埋め込みテンプレート `dashboard_html()`（serve はリクエスト毎に生成）。`_projects.html` は CLI `dashboard` が出力する成果物で、原本は projects.py。

## 背景（なぜこの表記か）
TM タブの編集可否は `projects.py` の `_tm_editable(path,size)` が判定：
- **XTM フォルダー配下（`/xtm/`）** → 編集不可（公式コーパスを下書きで汚染しない方針）
- **60MB 以上（`_TM_EDIT_MAXSIZE`）** → 編集不可（巨大TMをブラウザで展開しない保護）

ED2710 の University(395MB)/Product(177MB) は両条件に該当＝個別編集は不可。ただし「TEP完了」では承認済みセグメントを由来TM（XTM含む）へ**末尾追記**する経路がある（`tm_writeback_lib.append_tus_streaming`、全読み込みせず `<tu>` 追記）。＝「手で書き換えは禁止／機械的な承認済み追記のみ許可」という使い分け。この実態に表記を合わせた。

## 変更1：「読み取り専用」→「一括更新」
`projects.py` の UI 文字列を置換（+ `_projects.html` 再生成）。
- ドロップダウン項目ラベル： `… ・読み取り専用` → `… ・一括更新`
- 選択中TMの状態表示： `読み取り専用（XTML/サイズ）` → `一括更新（TEP完了で追記）`
- 一覧行の操作欄： `読取専用` → `一括更新`
- `#tmsel` ツールチップ： `XTML は読み取り専用` → `XTM は一括更新のみ`
- 編集拒否エラー： `編集できません（XTM 読み取り専用／サイズ超過）` → `個別編集できません（一括更新のみ・サイズ超過）`
- ※ `_tm_editable` の docstring（コード内コメント L897）の「読み取り専用コーパス」は内部説明のため残置。

## 変更2：役割ラベルの簡素化（メイン以外は TM 名のみ）
ドロップダウンのラベル生成（`projects.py` L2259 付近）を変更。
- 変更前： `r.name + " [" + r.role + "]" + …`（全TMに `[メインTM]`/`[Product TM]`/`[サブTM]`）
- 変更後： `r.name + (r.role==="メインTM" ? " [メイン]" : "") + …`
- 結果：**メインTMのみ `[メイン]` を付与**、Product／サブは **TM名のみ**表示（「Product TM」「サブTM」ラベルは非表示に）。
- 内部 role 値（`_tm_rows` の "メインTM"/"Product TM"/"サブTM"）や、プロジェクトサマリーの「サブTM N件」等のカウント表記は未変更（表示用件数なので温存）。

## 検証・同期
- `python -I -m py_compile projects.py` → OK。
- `python -I projects.py dashboard --out _projects.html` で再生成。配信HTMLに「一括更新」含有を確認（HTTP 200）。
- `Apps-local` → `GitHub-production` に `projects.py`／`_projects.html` をコピー同期。**未コミット**（保存のみ）。
- ハブ再起動（旧 python プロセス停止→`起動_Kotonoha-ハブ.bat` 再起動、http://127.0.0.1:8765/ HTTP 200）。※serve は旧コードをメモリ保持するため、コード変更時は再起動が必要（F5 のみでは不可）。

## NEXT
1. ブラウザ F5 → TM タブで新表記確認。
2. ED2710（`proj-20261021-163537`／`Creating DataFlows in Magic ETL`・280セグメント・MT58反映済み）の「実行/再開」で `_kotonoha\Creating DataFlows in Magic ETL.html` を開く → レビュー・確定（自動保存）。
3. 「TEP完了」（由来TMへ書き戻し＋完了）または「出力」（翻訳版JSON。⚠️ `2_For review` は元ソース上書きの恐れ→残すなら `3_Final`／任意フォルダー）。
4. 区切りで `git add`/commit（現状すべて未コミット）。

## 関連
- `作業ログ_20261023_Kotonoha-beta5-中間生成物と詳細パネル.md`（beta5 系）
- マニュアル `Kotonoha-beta6-マニュアル_Rev6.30.md`（現状記録・原本は .md）
