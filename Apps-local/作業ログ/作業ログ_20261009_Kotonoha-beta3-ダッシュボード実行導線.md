# 作業ログ 2026-10-09 — Kotonoha beta3（ダッシュボード実行導線＋サーバーモードでの作成・実行）

## 概要
昨日(10/08)の残タスク「ダッシュボード `_projects.html` の `type:"project"`（定義）行に実行導線」を実装。`_projects.html` は**サーバーのない静的HTML**でブラウザから直接バッチ/Pythonを起動できないため、方式は**コマンドコピー方式**（ユーザー選択）を採用。定義行に「実行」ボタンを追加し、クリックで**解析＋Pre-translation の実行コマンド**をクリップボードへコピー＋トースト表示する。実行自体は従来どおりターミナル貼り付け、またはランチャー [P]→G→番号で行う。

## 1. 変更ファイル
| ファイル | 変更 |
|---|---|
| `projects.py`（`dashboard_html`） | 定義行データに `pid`／実行コマンド `cmd` を付与。操作列を「html行＝開く／定義行＝実行ボタン」に分岐。`.run` ボタン CSS・`#toast` CSS・`copyText()`(clipboard→execCommand フォールバック)・`toast()`・`#rows` のクリック委譲を追加。冒頭説明文を更新。 |

## 2. 実装詳細
- **採番整合**：`list`/`idof`/`get`/`dashboard` はすべて `ordered(projects)` を `enumerate(...,1)` で回すため、ダッシュボードの `#` 列＝[P] の番号＝`idof --index N`。ボタンのツールチップに「[P]→G→番号 N」を明記。
- **実行コマンド生成**（Python 側で組立→JSON 埋込。パス空白は `"..."` で引用）：
  `python "<beta3>\projects.py" run --id <pid>`（＋ `_paths.cfg` に `CACHE=` があれば `--cache-dir "<cache>"`）。
- **キャッシュ再利用**：`_paths.cfg` 無しで `--cache-dir` 省略でも、エンジン `tm_match_analysis.py` の `--cache-dir` 既定 `DEFAULT_CACHE`（`...\___Working\Kotonoha\Index`）がランチャー既定 CACHE と**同一パス**のため、同じ索引キャッシュを再利用（遅延なし・パスの二重管理なし）。
- **file:// 対策**：静的HTMLをローカルで開くと `navigator.clipboard` が使えないブラウザがあるため、`document.execCommand('copy')` へフォールバック。失敗時はトーストにコマンド全文を表示して手動コピー可能に。

## 3. 検証
- `py_compile` OK。
- 隔離ストアの合成データ（`create`＋`add-source`）→ `dashboard` 生成を確認：
  - `const P` に定義行の `pid`＝`proj-...`、`cmd`＝`python "...\projects.py" run --id proj-...` が正しく出力。
  - `.run{` CSS・`button.run` ハンドラ・`function toast`・`function copyText` の存在を確認。
- **実台帳 `_projects.json`（3件）で実 `_projects.html` を再生成**：定義行「Test 001 - 1007」に実行コマンド1件が入り、html行2件（DomoStats Connector／Changes in Account...）は従来どおり「開く」。
- ※ ボタンのクリック→コピー→トーストの描画確認はブラウザでの実機確認が必要（静的HTMLの実行時描画のため自動検証不可）。コードパス・データは検証済み。

## 3b. ローカルサーバー方式で「ブラウザからプロジェクト作成・実行」を追加
ユーザー要望「新規作成ボタンから、翻訳対象ファイルと TM を指定するダイアログで、アプリ UI 上でプロジェクトを作成」。静的HTMLでは（1)ファイル書き込み不可・(2)`<input type=file>` が実パスを渡さない（`C:\fakepath`）ため不可能 → **ローカルHTTPサーバー方式**を採用（ユーザー選択）。

- **`projects.py serve`（新規）**：Python 標準 `http.server`（`ThreadingHTTPServer`）を **127.0.0.1 限定**で起動（外部非公開）。空きポート自動探索（既定 8765〜）。起動時に `webbrowser.open`。ランダム `token` を発行し、ページに埋め込み＋`/api/*` は `X-KT-Token` ヘッダ必須（他サイトからの CSRF 防止）。`--port/--engine/--template/--cache-dir/--store` 対応。
  - ルート：`GET /`＝サーバーモードのダッシュボード、`GET /api/projects`＝行データ、`GET /api/browse?dir=&kind=tmx|source|dir`＝サーバー側ファイルブラウザ（_paths.cfg の UNIV/PROD/SDIR/ODIR からクイックルート生成）、`POST /api/create`＝定義作成、`POST /api/run`＝解析実行（capture）。
- **リファクタ**：`run` のロジックを関数 `run_project(...)`（CLI と serve で共用）へ抽出。`create_project_full(...)`／`read_cfg()`／`build_rows()`（ダッシュボード表と `/api/projects` で同一形）を新設。`run` CLI ブロックは薄い呼び出しに。
- **ダッシュボード二重モード**：`dashboard_html(projects, served, token)`。`window.__KT={served,token}` を埋込。`served` の時だけ body に `served` クラス＋バッジ表示、`新規作成`＝作成ダイアログ、定義行「実行」＝`POST /api/run`（真のワンクリック）＋`refresh()` で再描画。静的 file:// 時（`served:false`）は従来どおり（新規=案内ノート、実行=コマンドコピー）。作成ダイアログはモーダル＋サーバー側ファイルブラウザ（名前・ソース複数・メインTM・ProductTM・サブTM）、`作成のみ`／`作成して実行`。
- **ランチャー**：メニューに `[D] ダッシュボードを開く（ブラウザで作成・実行／ローカルサーバー）` 追加 → `python projects.py serve --cache-dir/--template/--engine`。Ctrl+C でメニューへ戻る。
- **検証**：隔離ストア＋合成データでサーバー起動→API 通し：`GET /` で `served=true`＋token、**無トークン=403**、`/api/projects`（空→作成後2行）、`/api/browse`（dirs/tmx/roots）、`/api/create`（定義作成）、`/api/run`（ok=true・1記事登録・実際に解析実行）を確認。`py_compile` OK。ランチャー起動スモーク exit 0・`[D]` 表示。静的 `_projects.html` 再生成（`served:false`・既存動作維持）。テスト出力（Kotonoha-out\Serve Test）は削除。
  - ※ ブラウザ上の作成ダイアログ/ファイルブラウザの描画・クリック動作は**実機ブラウザでの確認が必要**（サーバー側APIは検証済み、クライアントJSの実時描画は自動検証不可）。

## 3c. ファイル指定を Windows ネイティブダイアログに
ユーザー要望「ファイルの指定は Windows のコンポーネントで」。ブラウザの `<input type=file>` は実パスを返さないため、**サーバー側で `tkinter.filedialog` を別プロセス起動**して Windows 標準の「ファイルを開く／フォルダー参照」ダイアログを表示し、選択した絶対パスをブラウザへ返す方式にした（サーバーはユーザー自身のPCなので、使い慣れた Explorer 選択で実パスが取れる）。

- `projects.py`：ヘルパースクリプト `TK_PICK`（`sys.executable -c` で別プロセス実行＝HTTPサーバースレッドでの Tk 競合回避、`-topmost` で前面化）。serve 起動時に `HAS_TK` 判定、`POST /api/pick {kind:tmx|source|dir, multiple}` → `{available, paths}`。tkinter 不在時は `available:false`。
- クライアント：作成ダイアログの「ファイル追加（複数可）」「フォルダー追加」「メイン/Product TM 選択」「サブ TM 追加（複数可）」を `/api/pick`（ネイティブ）に変更。`available:false` の時のみ従来のサーバー側HTML一覧 `openBrowser` に自動フォールバック。
- 検証：`py_compile`（projects.py・TK_PICK ヘルパー個別）OK、`tkinter` 利用可（Tk 8.6）、クライアント配線（`pick()`/`addF`/`/api/pick`）確認、サーバー再起動ブート OK。※ ダイアログ自体の表示・前面化・選択は**実機で要確認**（自動テストは対話待ちでブロックするため未実行）。

## 3d. 多フォーマット対応 Phase 1：txt の往復（元形式で翻訳版を出力）
要望「対象ファイルを md/mdx 以外（doc/docx/xls/xlsx/ppt/pptx/txt/テキスト系/PDF）へ」。方針＝**元のフォーマットで翻訳版を出力（往復）／容易なものから、困難（PDF・旧バイナリ）は後回し**。Phase 1 として依存なしの **txt 往復**を実装。
> 重要な前提：現ツールはどの形式でも「翻訳後の文書ファイル」を生成していない（成果物は TEP HTML＋TM）。往復は**新しい出力ステージの新設**。各形式に (1)位置保持の抽出 (2)再挿入ライター (3)翻訳適用 が必要。

- **新規 `doc_io.py`**：形式レジストリ。`extract(path)->[{uid,text}]` / `apply(path,out,trans)`。Phase 1=`.txt`（行=ユニット、空行・インデント・改行コード保持）。docx/xlsx/pptx は後で REGISTRY に追加（要 pip）。
- **新規 `doc_export.py`**：TM を文単位で適用して**元形式で翻訳版を出力**する往復ステージ。`tm_index`（`norm`/`exact_target`）を再利用し解析エンジンと同じキーで照合。`--source/--source-manifest --tmx --sub-tmx --cache-dir --out-dir [--mark-missing]`。出力は `OUT/translated/<rel>` に原拡張子で生成。**TEP 書き戻し後（TM が確定訳を保持）に走らせる想定**。未訳文は既定でソースのまま（`--mark-missing` で 〔未訳〕）。
- **設計上のデフォルト（要確認）**：訳文の出所＝**プロジェクトTM**（exact/100%）。pre-translation→MT→TEP→writeback 後の TM 適用で全文訳出になる。MT 確定前（mt-done 時点）の下書き出力が必要なら別途対応。
- **検証**：合成 txt（空行・インデント・1行2文・TM未収録文混在）＋TM で `doc_export`：「Title Line→タイトル行」「空行保持」「"Configure the dataflow. Save your work."→"データフローを構成します。 作業を保存します。"（**インデント保持・複数文再組立**）」、未訳文はソース維持、カバレッジ 4/5=80%。`--mark-missing`＝〔未訳〕付与、未対応 .docx はスキップ明示。`py_compile` OK（doc_io/doc_export）。既存コードは無変更。

## 3e. 多フォーマット Phase 2：「元形式で出力」導線を launcher/dashboard へ（※セッションクラッシュ→別インスタンスで復旧）
本ログを 16:36 に書いた**後**（projects.py 最終更新 16:44）に Phase 2 の導線追加へ着手。作業中にそのセッションが**クラッシュ**し、`TM-Match-Explorer.bat` への最後の編集が未適用で中断。別インスタンスでトランスクリプト（`...GitHub-Folder\de18fa80...jsonl`）を解析して中断箇所を特定し、復旧・完成させた。

- **判明した状態（クラッシュ時点）**：
  - `projects.py`＝**保存済み・py_compile OK**。追加済み＝CLI サブコマンド `export`（`export_project()` L301／L989、`doc_export.py` 呼び出し）、serve 側 `POST /api/export` ハンドラ（L1132）、ダッシュボード served モードの「出力」ボタン（CSS `.exp` L462-464／クリックハンドラ L619-624／`/api/export` fetch）。→ **py 側は内部完結**。
  - `TM-Match-Explorer.bat`＝ランチャー `[P]` の「元形式で出力」導線が**未適用**（最後の Edit を発行した直後にクラッシュ、`:projects_export` 本体は未着手）。bat は 15:56 版のまま。
- **復旧内容（bat 完成）**：
  - `:projects_menu` に `X = 元形式で翻訳版を出力 (TM適用／TEP書き戻し後に実行)` を追加。操作プロンプトに `X`、`if /i "%PA%"=="X" goto projects_export` を追加（L457/L461/L465）。
  - `:projects_export` サブルーチン新設（L505-527）：番号入力 → `idof --index` で定義ID解決（`:projects_run` と同流儀）→ 定義行でなければエラー戻し → `choice YNC` で〔未訳〕マーク要否（Y=付ける/N=付けない/C=戻る）→ `python "%PROJECTS%" export --id "!RID!" --cache-dir "%CACHE%" [--mark-missing]` → `projects_menu` へ戻る。
- **検証**：bat は CRLF 628行・LF混入0・BOM なし（CRLF 必須を遵守）。アンカー4箇所が各1回一致で挿入。bat が呼ぶ経路 `python projects.py export --id <不存在>` → `ERROR: project definition not found` ＋ exit 1 で graceful。バックアップ `TM-Match-Explorer.bat.bak_20261009` 作成。
- ※ 実機確認は未（ランチャー `[P]→X` の対話フロー、ダッシュボード served の「出力」ボタン描画・クリック）。

## 4. 残タスク（次回）
- マニュアル更新：[C]＝作成+実行・[1]/[2] 廃止・`--sub-tmx`/`--source-manifest`/`product_tm`/`run`/`idof`・**ダッシュボード定義行の「実行」ボタン**・**[D] サーバーモード（ブラウザで作成・実行）**を反映。Rev は **3.00** 候補（整数部+1）だが付番は要相談。
- （任意）補助メニュー番号 [3]–[9] の連番整理。
- ※ 実機確認：file:// 時のダッシュボード「実行」ボタン（コピー＋トースト）／[D] サーバーモードの作成ダイアログ・ファイルブラウザ・ワンクリック実行。
- （検討）サーバーモードでの状態/メモ/期日/削除の API 化（現状はランチャー [P]）。
- **多フォーマット Phase 2**：`doc_export` の launcher/dashboard 導線追加は**完了**（3e：CLI `export`／serve `/api/export`／ダッシュボード「出力」ボタン／ランチャー `[P]→X`）。残り＝pip 導入後に docx(python-docx)/xlsx(openpyxl)/pptx(python-pptx) の extract/apply を REGISTRY へ。PDF（PyMuPDF・抽出のみ、往復は実質不可）・旧 doc/xls/ppt（要事前変換）は後回し。往復の訳文出所（TM か mt-done 併用か）をユーザー確認。
- ※ 実機確認（本日分の未確認）：ランチャー `[P]→X`（元形式で出力）の対話フロー、ダッシュボード served の「出力」ボタン描画・クリック。
- （整理）不要なら復旧時のバックアップ `TM-Match-Explorer.bat.bak_20261009` を削除。
