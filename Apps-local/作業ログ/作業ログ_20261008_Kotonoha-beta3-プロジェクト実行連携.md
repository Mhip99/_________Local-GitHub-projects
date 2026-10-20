# 作業ログ 2026-10-08 — Kotonoha beta3（プロジェクト定義の解析＋Pre-translation 実行連携）

## 概要
昨日(10/07)の残タスク1を実装。**保存済みプロジェクト定義（[C] ウィザードが作る `type:"project"`）をそのまま解析＋Pre-translation に流す実行連携**を追加した。複数ソース（ファイル／フォルダー混在）・フォルダー階層維持の出力・メイン＋複数サブ TM での索引・`combined.mt-todo` 生成までを定義ドリブンで実行できる。

> 設計判断（本日決定）：プロジェクトの **サブ TM（複数）は「マッチ用」**（`is_product=False`、メイン TM と同じ exact/fuzzy マッチ源）として扱う。Product（用語集ヒント）扱いにはしない。

---

## 1. 解析エンジン `tm_match_analysis.py`
- **複数マッチ TM**：`--sub-tmx <tmx...>` を追加。索引 specs は `main(False) + sub(False)… + product(True)`。索引コア `tm_index.load_or_build` は元々 `(path,is_product)` の任意本数リストを受けるため、CLI 拡張のみ。
- **階層維持出力**：`--source-manifest <json>` を追加。`{"sources":[{"src":<abs .mdx>,"rel":<出力ステム。/ がサブフォルダー>}]}` を受け、出力を `--out-dir/<rel>.html` に生成（サブフォルダー自動作成）。既存の `--source`/`--source-dir`/`--out`/`--out-dir` 挙動は不変（[1]/[2] 後方互換）。
- **記事キーの一意化**：`art_key` を「`--out-dir` からの相対パス（`/`→`__`）」に変更。別フォルダーの同名ファイル衝突を回避。`combined.mt-todo` の `segments[].art` と `articles[].art` は従来どおり整合。

## 2. 台帳 `projects.py`
- **`run --id <pid>`**（新規）：定義を読み、ソースを manifest に展開（file＝ステム、dir＝再帰走査しフォルダー名で根付けして階層維持）→ エンジンを subprocess 実行（`--tmx main` ＋ `--sub-tmx` 群 ＋ `--source-manifest` ＋ `--combined-todo`）→ 生成記事を `upsert` で台帳登録＋定義の `status` を 未解析→作業中、`out_dir`/`combined`/`last_run` を記録。引数 `--engine`/`--template`/`--cache-dir`/`--path`(出力先上書き) を追加。
- **`idof --index N`**（新規）：一覧 N 行目が `type:"project"` のときだけ `id` を出力（ランチャーが実行対象を特定するため）。

## 3. ランチャー `TM-Match-Explorer.bat`
- **[C] 作成後にそのまま実行**：定義保存後 `Y/N` で「今すぐ 解析＋Pre-translation」。共通ラベル `:run_proj`（`!PID!` を使用、`combined.mt-todo` 出力→登録→ダッシュボード再生成）へ。
- **[P] に `G=実行`**：番号から `idof` で定義 id を解決し `:run_proj`（戻り先 `RUNRET=projects_menu`）。
- メイン [C] 説明を「作成+実行」に更新。`^<=74%%` 等の表示エスケープ対応。

## 4. 成果物（変更ファイル）
| ファイル | 変更 |
|---|---|
| `tm_match_analysis.py` | `--sub-tmx` / `--source-manifest`、階層出力、`art_key` 一意化 |
| `projects.py` | `run` / `idof` コマンド追加、引数 `--engine/--template/--cache-dir` |
| `TM-Match-Explorer.bat` | [C] 即実行・`:run_proj`・[P] の `G=実行`・メニュー文言 |

## 5. 検証（合成データで通し）
- 一時プロジェクト（ネストした .mdx を含む dir ソース＋単一 file ソース、main.tmx＋sub.tmx、隔離ストア）で `run` を実行し、全チェーンを確認。実機 `_projects.json` は未変更（`--store` 隔離）。
- **複数 TM**：main.tmx＋sub.tmx を 1 索引に構築。`intro`→main 由来100%（これは序章です）、`details`→**sub 由来100%**（詳細は以下のとおりです）を注入確認＝サブ TM がマッチに寄与。
- **階層維持**：`out/src/guide/intro.html`・`out/src/guide/sub/details.html`・`out/single.html` を生成。
- **combined.mt-todo**：記事3・MT6、`art` キー一意（`src__guide__intro` / `src__guide__sub__details` / `single`）。
- **登録**：定義=作業中、記事3行を台帳登録。
- **下流注入 [4]**：捏造 `combined.mt-done.jsonl`（gi 6 件）で一括注入 → 3 記事とも filled 2/2・2/2・2/2、still empty 0。
- `py_compile`：3 スクリプト OK。空プロジェクトの `run` は `ERROR: project has no sources`（exit 1）でクリーン停止。
- ※ `choice` を含むウィザード通しの自動テストは従来どおり不可（実機キーボードで確認する運用）。`run` 自体はコンソール直実行で検証済み。

## 5b. 追加修正：JSX `title="..."` のセグメント抽出バグ
実記事（`___Test Projects\EN source\000005214\000005214.mdx`）で [1] を実行中に発覚。`<Accordion title="...">`（FAQ 設問）の訳文が、
- 1 文タイトル → 行全体が `<...>` タグ扱いで `norm` が空になり**丸ごと欠落**、
- 複数文タイトル → 文分割がタグ途中で起き `<Accordion title="...` / `What happened?">` の**破損セグメント**、
になっていた（6 設問の大半が翻訳対象から漏れ）。
- 対策：`read_segments` を改修。各行で**タグ除去の前に** `title="..."` / `title='...'` を文書順に抽出（`TITLE_ATTR`）→ その後 `<[^>]+>` を一括除去。`title` 限定なので `<img alt="ファイル名">` 等は対象外。
- 検証：当該記事で再実行 → 全 37 セグメント（ICE 28/100% 7/95-99% 1/85-94% 1、MT 0）。`What happened?` は ICE で単独セグメント化、破損 0、6 設問すべて抽出を確認。

## 5c. 本日の [1] 実機実行（単一記事）
- `000005214.mdx`（title: Changes in Account Configuration Requirements for Connectors）を University＋Product TM で解析。索引キャッシュ HIT（1.2s, keys 258,731）。
- 出力 `CAT tool\CAT\TM-Match-Explorer-Changes in Account Configuration Requirements for Connectors.html` を生成し台帳へ登録（作業中）。再利用率 100%・MT 0。

## 5d. UI 統合（[1]/[2] → [C]/[P] 一本化）＋ Product TM 対応
解析＋Pre-translation の入口を **[C]（作成＋実行）/[P]（再開・実行）に一本化**し、旧 **[1]/[2] をメニューから削除**（タイプ入力 `1`/`2` は案内して [C] へ誘導）。回帰防止のため **プロジェクト定義に `product_tm` 枠を追加**（＝残タスク4も同時解消）。
- `projects.py`：`set-product-tm` 追加、`create`/`show`/`dashboard` に product_tm 反映、`run` が存在すれば `--product-tmx` を付与（用語集ヒント維持）。
- `TM-Match-Explorer.bat`：メニューを [C]/[P] 主役に再構成し [1]/[2] 削除、`:moved12` 誘導、[C] ウィザードに **(3) Product TM** ステップ追加（既定＝Product TMX、S でスキップ）、既定を メイン=University／Product=Product／サブ=未設定 に修正、[P] で定義行の番号を開こうとしたら実行(G)へ誘導、文言の [1]/[2]・Pass 表記を解消。
- 検証：隔離ストアの合成データで `run`（Product TM 有）→ エンジンが Product を索引化（product terms:1）、MT セグメントに用語集ヒント `Magic ETL` 付与、`show`/ダッシュボードに Product TM 表示。ランチャーは起動スモーク（menu→Q）で exit 0・構文エラーなし、新メニュー表示を確認。`py_compile` OK。
- ※ `choice` を含む [C]/[P] の対話通しは従来どおり実機で確認する運用（リダイレクト入力では `choice` が EOF エラーになるため）。

## 6. 残タスク（次回）
- ~~[1]/[2] を [C]/[P] へ統合（UI 統一）~~ → §5d で完了。
- ~~run の Product TM 対応~~ → §5d で完了（定義に product_tm 枠追加）。
- ダッシュボード `_projects.html` の `type:"project"` 行に「実行」導線（現在は [P] コンソールの `G`、または番号選択→実行(G)誘導のみ。「開く」は html 行のみ有効）。
- マニュアル更新：[C]＝作成+実行・[1]/[2] 廃止・`--sub-tmx`/`--source-manifest`/`product_tm`/`run`/`idof` を反映。機能追加のため Rev は **3.00** 候補（整数部+1）だが付番は要相談。
- （任意）補助メニューの番号 [3]–[9] はそのまま。将来クリーンな連番にするか要検討。
