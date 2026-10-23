# 作業ログ 2026-10-23 — Kotonoha beta5：中間生成物の集約・自動プロジェクト化の廃止・詳細パネル・出力先選択

## 概要
ユーザー指摘（「プロジェクトを作成するのはユーザーのみ。勝手に自動生成しない」「ED2710 が複製されたように見える＝Kotonoha-out の出力フォルダー」）を受けて、生成物まわりを再設計。全変更は `Apps-local`（正本）→ `CAT tool\CAT\Kotonoha-beta5` に同期済み。未コミット。

## 実装（projects.py）
1. **中間生成物の保存先をプロジェクト配下に集約**
   - 新ヘルパー `project_root_for(path)` / `details_dir_for(p)` / `export_dest_for(p,out_path)`。
   - 作業サブフォルダー（`1_en`/`2_For review`/`3_Final`/`_kotonoha`/`_Details`）の親をプロジェクトルートとみなす。
   - `run_project` の出力先を `Apps-local\Kotonoha-out\<名前>` から **`<プロジェクト>\2_For review\_Details`** に変更（中間生成物＝TEP・manifest・combined・mt-todo/done・uidmap）。
2. **自動プロジェクト化を廃止**
   - `run_project` は生成記事を `upsert` で別プロジェクト行に登録しない。代わりに `p["artifacts"]=[{title,html,source,segs,mt}]` としてプロジェクトに記録。
   - 戻り値 `produced` は `[{title,html}]`（タブ自動表示用）。MT 再反映（`<html>.mt-done.jsonl`）は従来どおり。
3. **『詳細』パネル**
   - プロジェクト行のボタンを **[実行][出力][編集][詳細]** に。詳細クリックで行直下にサブセクション展開。
   - 新 API `GET /api/details?id=` → `project_details()`：作業サマリー＋`_Details` フォルダーのファイル一覧（TEP は「開いて編集」リンク、各ファイルに「開く」＝保存場所をエクスプローラー表示）。
4. **出力先の選択**
   - `GET→POST /api/export` に `out_path` を追加。モーダルで **2_For review / 3_Final / 任意フォルダー**（`openBrowser("dir")`）から選択。
   - `export_dest_for`：区切りなしの名前（例 `3_Final`）はルート下サブフォルダー、絶対パスはそのまま、未指定は `2_For review`。
   - JSON 出力は `p["artifacts"]` を走査し、記事の訳文を元 JSON に適用（100%。適用 280 を確認）。
5. **TEP をパスで配信**：`/article?path=<abs>`（`_serve_article_path`）。既知プロジェクトルート配下／旧 Kotonoha-out 配下のみ許可。最新テンプレートへ貼り替え＋KTトークン注入。

## データ移行
- 既存 `Apps-local\Kotonoha-out\ED2710-…\` を **移動**（robocopy /MOVE）→ `ED2710-…\2_For review\_Details\`。`Kotonoha-out` は空に。
- `_projects.json`：自動生成されていた記事行（proj-20261021-163710）を**削除**。ED2710 定義に `artifacts`／新 `out_dir`／`combined` を設定。
- `.gitignore` に `_Details/` を追加（中間生成物は非追跡。再実行で再生成可）。

## 注意（上書き）
- 出力先 **2_For review** は元ソース JSON と同じパス・同名になり得る＝**上書き**。元ファイルを残すなら 3_Final か別フォルダーを選択（モーダルに注意書きを表示）。今回のテストで一時上書き→`git checkout` で英語ソース復元済み。

## 検証（ポート8788で起動テスト）
- `/api/projects`：行数 **1**（ED2710 のみ。自動生成行なし）。
- `/api/details`：サマリー＋`_Details` 7ファイル（TEP=is_tep）。
- `/article?path=`：200・SEG あり・KT 注入・最新UI貼り替え（216KB）。
- `/api/export out_path=3_Final`：ok・mode=tep・applied=280・`3_Final\…json`(35KB) 生成（テスト後に削除）。
- `py_compile` OK。サーバー停止済み。

## 追補（同日・仕様変更）
- ユーザー指示: 中間生成物の保存先を `2_For review\_Details` → **`<プロジェクト>\_kotonoha`** に戻す（_kotonoha が無い別プロジェクトでは自動作成）。
- `details_dir_for` を `_kotonoha` に変更、`project_details` のルート算出を修正、詳細パネルのラベルを「_kotonoha」に。
- 現用の作業生成物（`<title>.html`＋uidmap/mt-done/mt-todo/combined/manifest）を `_Details`→`_kotonoha` に移動し、`_Details` フォルダーと旧 `translated/`・一時翻訳JSONを撤去。`_projects.json` の out_dir/combined/artifact html を `_kotonoha` に更新。`.gitignore` の `_Details/` 行を削除。
- 既存 `_kotonoha` に残る旧 `.TEP.html`（git追跡済み・2026-10-20生成）は残置（詳細パネルでは is_tep 非該当＝プレーン表示。クリックで開くのは artifacts の `<title>.html` のみ）。
- 再検証（ポート8789）: projects=1／details_dir=`…\_kotonoha`／is_tep=`Creating DataFlows in Magic ETL.html` のみ／`/article?path=` 200・SEGあり／export(3_Final) applied=280。CATへ同期済み。

## 追補2（同日・保存先の再変更／配信方式／用語／タグ修正）
- **保存先を `_kotonoha` に戻す**（ユーザー指示）。`details_dir_for`→`<プロジェクト>\_kotonoha`（無ければ自動作成）。現用生成物を `_Details`→`_kotonoha` に移動し `_Details`・`.gitignore` の `_Details/` を撤去。`_projects.json` を `_kotonoha` に更新。
- **旧TEPの隔離**: `_kotonoha` に同居していた旧 `.TEP.html` セット（2026-10-20・git追跡済み5ファイル）を `git mv` で **`ED2710…\_archive-old-TEP\`** へ退避（ごみ箱ではない＝追跡維持。ツール非参照フォルダー）。詳細パネルの TEP は artifacts の html と一致するもののみ「開いて編集」。
- **配信は貼り替えしない**: `/article`（`_serve_article`・`_serve_article_path`）から reskin を撤去し、生成 `.html` を**そのまま配信**（KTスクリプト1行のみ付与）。検証で KT 除去後 `-ceq` True＝ファイルと完全一致。最新UIは実行（再生成）で反映。
- **用語修正**: ファイル/データを「TEP」と呼ぶ表現（「TEP HTML」「生成/TEP HTML」等）を「作業ファイル（編集画面）」へ。TEP＝作業（工程）の意味の箇所は維持。コード識別子は非改名。
- **TMターゲットのインラインタグ正規化**: TM一致訳に残る `<x id="xN"/>` を `{N}` チップへ。`tm_match_analysis.py` に `norm_tm_tags()` を追加（exact/fuzzy両経路）。既存 html は51セグメントを一括パッチ（例 #13→`{1}{2}{3}{4}…`、#15 と同形式）。元 html バックアップ=`%TEMP%\CDF_pretag_backup.html`。
- 以上すべて `Apps-local`→`CAT\Kotonoha-beta5` 同期済み。**未コミット**（保存のみ、コミットは指示待ち）。

## NEXT
1. 起動bat → ハブ。ED2710 の **[詳細]** で `_Details` とサマリーを確認、TEP を開いて翻訳レビュー→自動保存。
2. **[出力]** で保存先（2_For review 上書き／3_Final／任意）を選択して翻訳版 JSON を書き出し。
3. 問題なければ `git add`/commit（現在すべて未コミット）。マニュアル本文の beta5 反映は保留継続。
