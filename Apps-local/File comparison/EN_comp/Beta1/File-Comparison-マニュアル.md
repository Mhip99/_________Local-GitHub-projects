# File Comparison — マニュアル

英語ソース（.mdx）の **現行版（Current）** と **前回翻訳した版（Target translated）** を比較し、
「どのファイルが変更され、再翻訳が必要か」を **Excel レポート**にまとめるツールです。

> 場所: `OneDrive - Domo Inc\________GitHub-production\File comparison\`

---

## 0. 何をするツールか

- 2つのフォルダー（現行版フォルダー ／ 前回翻訳版フォルダー）にある英語ソースを**ファイル単位で突き合わせ**ます。
- 両フォルダーの**和集合**が対象。現行にしか無い＝**New**、前回訳にしか無い＝**Not in C**（Current に無い）。
- 変更あり＝**Y**（要対応）、変更なし＝**N**、判定不能＝**?**。
- 結果は色分け・オートフィルター付きの Excel（2シート）で `__Results\` に出力されます。

翻訳ワークフロー上の用途: 「前回納品時のソース」から「今の最新ソース」へ**何が変わったか**を洗い出し、再翻訳対象（Y）を確定するための差分一覧を作ります。

---

## 1. 構成ファイル

| ファイル | 役割 |
|---|---|
| `File-Comparison.bat` | **ダブルクリック起動用**バッチ（`Run-FileComparison.ps1` を呼び出す） |
| `Run-FileComparison.ps1` | **実行時に Fullset / Project を対話選択**するランチャー（推奨） |
| `Run-Fullset.ps1` | Fullset 専用ランチャー（モード固定・選択不要） |
| `Run-Project.ps1` | Project 専用ランチャー（モード固定・選択不要） |
| `file_compare_fullset.py` | **比較エンジン本体**（ランチャーから呼ばれる） |
| `translatable_util.py` | 翻訳対象テキスト抽出モジュール（`--translatable-only` で使用） |
| `__Results\` | 出力先。`File_Comparison-…….xlsx` が溜まる |

**動作要件**: Python 3.11（既定パス `C:\Program Files\Python311\python.exe`）＋ `openpyxl`。ランチャーは `.ps1`（PowerShell）。

---

## 2. Fullset と Project の違い

**比較ロジックは同一です。** モード名（Fullset / Project）は出力ファイル名の接尾辞（`--label`）にすぎません。
実務上の違いは「**どの前回翻訳スナップショットと比較するか**」で、用途に応じて名前を分けています。

| モード | 想定用途 | 出力名の例 |
|---|---|---|
| **Fullset** | ドキュメント全体（フルセット）の前回訳版との比較 | `File_Comparison-Fullset_YYYYMMDD-MMDD.xlsx` |
| **Project** | 特定プロジェクトのスナップショットとの比較 | `File_Comparison-Project_YYYYMMDD-MMDD.xlsx` |

同日に両方を実行してもファイル名が衝突しないよう、ラベルで区別しています。

---

## 3. 使い方（ランチャー・推奨）

起動方法は2通りあります。

### 方法A（最も簡単）: バッチをダブルクリック
`File-Comparison.bat` を**ダブルクリック**すると、`Run-FileComparison.ps1` が起動します。
実行ポリシーの回避や PowerShell の選択（pwsh 優先）はバッチ側で処理します。

### 方法B: PowerShell から実行
`.ps1` 単体は**ダブルクリックでは実行されません**。次のいずれかで起動します。

- 右クリック →「**PowerShell で実行**」
- フォルダーで PowerShell を開いて実行:

```powershell
cd "…\________GitHub-production\File comparison\Beta1"
.\Run-FileComparison.ps1
```

実行ポリシーで `.ps1` がブロックされる場合:
```powershell
powershell -ExecutionPolicy Bypass -File ".\Run-FileComparison.ps1"
```

### 対話の流れ（A・B 共通）
1. **モード選択**（`[1] Fullset` / `[2] Project`）
2. **Last translated（前回翻訳版）フォルダーのフルパス**を入力

### s\article の自動採用（s\article を優先）
対象ファイルの親フォルダーは常に `\article`（＝`s\article`）です。入力フォルダーから次の**優先順**で対象を解決します。

1. **`<入力フォルダー>\s\article` があれば最優先で採用**（スナップショットのルートを渡した場合。ルート直下に無関係な `.mdx`（例: テンプレート）が数個あっても、`s\article` を優先します）
2. 無く、かつ**入力フォルダー自体に `.mdx` がある**場合は、それを article フォルダーとみなしてそのまま使用（`…\s\article` を直接指定した場合）
3. どちらも該当しなければ、**配下を再帰的に検索して `s\article`（親が `s` の `article`）を採用**

そのため、スナップショットの親や上位フォルダーを渡すだけでも対象の `article` に到達します。想定される構成:
```
…\domo-documentation-hub-main_MMDD\s\article
…\domo-documentation-hub-main_YYYYMMDDMMDD\s\article
```
（`MMDD` / `YYYYMMDDMMDD` は日付形式）

- 再帰検索で `s\article` が**複数**見つかった場合は、最上位（パス最短）を採用し、候補を警告表示します。
- `s\article` が**1つも見つからない**場合はエラーで停止します。

---

## 4. 使い方（コマンドライン）

ランチャーを介さず、エンジンを直接実行することもできます。

```powershell
python file_compare_fullset.py "<前回翻訳版フォルダー>" --label Fullset
```

| 引数 | 説明 |
|---|---|
| `target_translated`（位置引数・必須） | 前回翻訳した英語ソースのフォルダー（例 `…\domo-documentation-hub-0608\s\article`） |
| `--current PATH` | 現行版フォルダー。既定＝`…\_________GitHub-Main\domo-documentation-hub\s\article` |
| `--results PATH` | 出力フォルダー。既定＝`…\File comparison\__Results` |
| `--label TEXT` | 出力ファイル名の接尾辞（`Fullset` / `Project` など） |
| `--translatable-only` | **翻訳対象テキスト（タイトル＋本文散文）の変更だけを Y** と判定。マークアップ/メタの変更は無視して Note に要約（§7） |

ランチャーからは `-Mode` / `-LastTranslated` / `-Current` / `-Results` / `-TranslatableOnly` で同じ引数を渡せます:
```powershell
.\Run-FileComparison.ps1 -Mode Project -LastTranslated "C:\…\s\article" -TranslatableOnly
```

---

## 5. Update 区分（判定結果）

Excel の **Update 列**が各ファイルの判定です。

| 値 | 意味 | 色 |
|---|---|---|
| **Y** | 変更あり（**要対応**）。リネームも Y 扱い | 薄オレンジ |
| **N** | 変更なし（正規化後の内容が一致） | なし |
| **?** | 判定不能（読み取り／文字コードデコード失敗） | 黄 |
| **New** | 現行版にのみ存在（新規ファイル） | 薄緑 |
| **Not in C** | 前回訳版にのみ存在（Current に無い＝削除/移動の可能性） | グレー |

並び順は **Y → ? → Not in C → New → N**（各内はファイル名昇順）。

---

## 6. Summary 列（何が変わったか）

Y の行には、変更の種類が **Summary 列**に入ります（通常モード）。

- **Title** … フロントマターの `title` が変わった
- **Text body** … 本文（散文）が変わった
- **Tags** … HTML/MDX タグの変化を含む
- **Numbers** … 数字の変化を含む
- **Symbols** … 記号（`# % & @ * / \ () [] {} <> | ~ ^ = +`、各種ダッシュ/引用符）の変化を含む
- **File name（旧名 → 新名）** … リネーム検出（内容一致・名前変更）

---

## 7. `--translatable-only` モード（翻訳対象のみを対象化）

翻訳者が実際に触る**自然言語テキスト（タイトル＋本文散文）だけ**を変更とみなすモードです。
`translatable_util.py` が MDX/Markdown マークアップを除去してから比較します。

- **Y になる**：タイトル or 本文散文が変わった場合（Summary は `Title` / `Text body`）。
- **Y にならない（Note に要約）**：翻訳に影響しない差分は無視し、種類を **Note 列**に記載:
  - `excerpt` / `frontmatter`（title・excerpt 以外のメタ）
  - `import`（import/export 行）
  - `list marker`（`- * +` の箇条書き記号の種類）
  - `tag/markup`（HTML/MDX タグ）
  - `link/image path`（リンク/画像の URL・パス）
  - `code`（コードフェンス・インラインコード）
  - `spacing/line break`（空白・改行のみ）

除去対象: インラインコード、画像（alt だけ残す）、リンク（表示テキストだけ残す）、JSX式 `{…}`、
HTML/MDX タグ、見出し/引用/箇条書き記号、表の `|`、強調記号、コードフェンス、import/export 行。

---

## 8. 出力 Excel

### ファイル名
```
File_Comparison[-<LABEL>]_<実行日YYYYMMDD>-<前回訳版MMDD>.xlsx
```
- `<実行日>` … 実行した日。
- `<前回訳版MMDD>` … 前回翻訳版フォルダー内で**最も多いファイル更新日**の月日（スナップショット時期の目安）。
- 例: `File_Comparison-Fullset_20260901-0610.xlsx`（9/1 実行・前回訳は 6/10 版）。
- **同名ファイルが既にある場合**は、`-01`, `-02` … の**連番**を付けて保存します（例 `…-0610-01.xlsx`）。既存ファイルは上書きしません。
- **出力先フォルダーが存在しない場合**は、出力先パスの入力を求めます（対話実行時。Enter で既定パスを作成）。
- 保存先が Excel で開かれている等でロックされている場合は、`…_HHMMSS.xlsx`（時刻付き）の別名で保存し、結果を失いません（警告を表示）。

### シート
- **Comparison** … 全ファイル。
- **Changed (Y)** … Y の行だけを抜き出したシート。
- **Data**（最終シート）… 実行メタ情報。列は **Item / Note**。項目（英語）は `Current version folder`（現行版パス）／`Target translated folder`（前回翻訳版パス）／`Work date/time`（作業日時 `YYYY-MM-DD HH:MM:SS`）。

### 列
| 列 | 内容 |
|---|---|
| File name | ファイル名 |
| Article title | フロントマター `title` |
| Update | 判定（Y/N/?/New/Not in C） |
| Summary | 変更の種類（§6）または Not in C 等 |
| Changed | 変更ボリューム。`+N Words（+P.P%）` 形式（§8a） |
| Target translated date | 前回訳版ファイルの更新日 |
| Current date | 現行版ファイルの更新日 |
| Note | 補足（空白差の種類、判定不能理由、リネーム、`--translatable-only` の無視項目） |

書式: ヘッダー固定（freeze）、オートフィルター、全体に薄い罫線、Summary/Article title は折り返し表示、Update は色分け。

### コンソール出力
実行後、Current/Target/Common/Rename/Y/N/?/New/Not in C の件数と、
**Y のファイル一覧**・**? のファイル一覧（理由付き）**が表示されます。

## 8a. Changed 列（変更ボリューム）

変更の量を **`+N Words（+P.P%）`** の形式で表します（`N`＝変更語数(Words)、`P.P%`＝現行版に対する割合）。

- **語数(Words)のカウント**: 英語ソースを空白区切りの語（トークン）として、旧→新の語レベル差分を数えます。
  **追加も削除も「＋」**として数えます（例: 前回訳版にあった1語 `ABCDEFG` が現行版で削除 → `+1 Words`。現行版で新たに `ABCDEFG` を追加 → `+1 Words`）。
- **％の分母**: **現行版ファイルの総語数**。削除が多く現行版が短い場合は 100% を超えることがあります（分母＝現行版の総語数のため）。現行版が0語（空）のときは 0.0%。
- **区分ごとの入り方**:
  - **Y（変更あり）**: 差分の語数と％。例 `+5 Words（+55.6%）`。
  - **New（現行版のみ）**: 対象テキスト**全量**の語数。現行版比なので **`+100.0%`**。
  - **Not in C（前回訳版のみ）**: **空欄**（記入不要）。
  - **N（変更なし）**: **空欄**。
  - **?（判定不能）**: **空欄**（読み取り不可のため数えられない）。

> 注: 語数は空白区切りトークン基準のため、マークアップ記号も1語として数えられます。翻訳対象テキストのみで測りたい場合は今後 `--translatable-only` 連動の拡張余地があります。

---

## 9. 判定の内部ロジック（参考）

- **正規化比較**: 改行（CRLF/CR→LF）と行末空白・末尾空行を除いて内容比較。
  - 正規化後が一致 → **N**（生の差だけあれば Note に `Hard line break` / `Space`）。
  - 正規化後も相違 → **Y**（Summary に変更種類）。
- **リネーム検出**: 内容が完全一致で名前だけ違うファイル（旧のみ↔現行のみ、1対1）を **Y / File name** として検出。
- **文字コード**: `utf-8-sig` → `utf-8` → `cp932` の順で読み取り。全滅時は置換して `?`（decode-error）。
- **タイトル抽出**: フロントマター `title:`（`"..."` / `'...'` / 素の値）から取得。

---

## 10. 注意点

- 比較は**ファイル名一致**が基本。名前が変わると（内容一致なら）リネームとして検出、内容も変われば New＋Not in C の2行に分かれます。
- `Target translated date` は個々のファイルの更新日、ファイル名の `MMDD` はフォルダー内の**最頻更新日**です（一致しないこともあります）。
- 既定の Current フォルダーはハードコードされています（`_________GitHub-Main\domo-documentation-hub\s\article`）。別の現行版を使う場合は `--current` で指定してください。
- `--translatable-only` は「マークアップだけの変更で再翻訳対象にしたくない」場合に有効。逆に、タグや数値の変更も検知したい通常確認では付けません。
