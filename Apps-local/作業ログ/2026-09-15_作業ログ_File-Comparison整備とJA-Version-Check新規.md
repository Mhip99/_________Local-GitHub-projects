# 作業ログ 2026-09-15 — File Comparison 整備 ＋ JA Version Check 新規作成

対象: `________GitHub-production\CAT tool\CAT\` および `…\File comparison\`

---

## 1. 環境整備
- **pandoc 3.11 インストール**（winget `JohnMacFarlane.Pandoc`, `%LOCALAPPDATA%\Pandoc\pandoc.exe`, ユーザーPATH）。マニュアルの `.md`→`.docx` 変換に使用。
- 共通スタイル原本 **`CAT tool\CAT\_assets\pandoc-reference.docx`**（本文=Yu Gothic / コード=Consolas）を作成し、各ツールの docx 生成で `--reference-doc` に使用（同梱＋マスター方式）。
- **教訓**: 日本語入り `.bat` は **CRLF** 必須（LF だと cmd が誤解析）。日本語入り `.ps1` は **UTF-8 BOM** 必須（BOMなしだと Windows PowerShell 5.1 が cp932 誤読）。

## 2. Kotonoha beta2 マニュアル
- `CAT\Kotonoha-beta2\Kotonoha-beta2-マニュアル.docx` を pandoc で生成（既存 .md から）。

## 3. File Comparison（英語ソースの Current vs 前回翻訳版比較）
- 対話式ランチャー **`Run-FileComparison.ps1`** 追加（実行時に Fullset/Project を選択）。
- マニュアル `File-Comparison-マニュアル.md`/`.docx` 作成。
- **版分け**: `File comparison\` 直下に `Alpha`（修正前）/ `Beta1`（修正後）を作成し自己完結化。旧 `Run-FileComparison-old.ps1` は Beta1 から削除（Alpha に保持）。不要ファイル（旧 HTML/旧 tm_match_analysis.py）削除。
- **Beta1 の機能追加**:
  - **Changed 列**（D と E の間）: 変更ボリュームを `+N Words（+P.P%）` 表記（当初「語」→「Words」に変更）。追加も削除も＋。%分母=現行版総語数（削除多いと100%超あり／空は0%）。New=全量(+100%)、Not in C/N/?=空欄。
  - **Data シート**（最終）: 列 Item/Note、English/Current/Published 各フォルダー・作業日時。項目は英語表記。
  - **前回翻訳版の自動採用を再帰化＋s\article 優先**: `<入力>\s\article` を最優先→無ければ配下再帰検索。ルート直下に無関係な .mdx があっても s\article を優先（誤って root を比較する不具合を修正）。
  - **同名ファイルは `-01,-02` 連番**（上書きしない）、**出力先フォルダー未存在は対話で尋ねる**（非対話時は作成）、**ロック時は `…_HHMMSS.xlsx` 別名保存**。
- **出力先フォルダーを `Results` → `__Results` にリネーム**（Beta1 の `DEFAULT_RESULTS` も更新）。
- **移動**: `Beta1`/`Alpha` を **`File comparison\EN_comp\`** 配下へ移動（動作確認済み。ランチャーは `$PSScriptRoot` 基準・エンジンの絶対パスは対象外のため無障害）。
- 実行例（Fullset, 前回訳=`…\domo-documentation-hub-main-0519\s\article` 1796件, 現行1850件）: Y=1794 / New=56 / Not in C=2。

## 4. JA Version Check（新規ツール） — `File comparison\JA_comp\`
**目的**: 最新の日本語版が英語版と同じバージョンかを判定（英語版が更新され日本語版が古いまま等を検出）。

**構成**: `JA-Version-Check.bat`（ダブルクリック）→ `Run-JAVersionCheck.ps1`（説明→実行確認→Published JA パス入力）→ `ja_version_check.py`（本体）＋ `tm_ja_en.py`（TM JA→EN 索引）。マニュアル `.md`/`.docx` あり。

**対象（既定）**: EN=`…\domo-documentation-hub\s\article`(1850) / JA=`…\ja\s\article`(1383)。frontmatter は title/excerpt のみ（版数フィールド無し）。

**対応付け**: ①同名（コード）=Match rate 100% ②名前違い=画像パス一致率 ③TM で JA 本文→英語原文を引き EN ファイルを探索。**リンクURLはローカライズ差（/jp/）のため現状は判定に不使用**、画像パス＋git 日時＋TM で判定。

**Update 判定**: git 最終コミット日時（EN>JA）＋内容構造（EN に JA へ無い画像）の**併用**。git.exe は PATH 無しのため自動解決（`%LOCALAPPDATA%\Programs\Git\cmd\git.exe`）。

**内容比較（多段）**: Pass1 で要注意ペアを `content-todo.json`（EN/JA 本文つき）に出力 → Pass2 で Claude が内容比較 → done.jsonl → Pass3 `--inject` で Excel 反映。

**出力**: `__Results\JA version\JA_version-YYYYMMDD.xlsx`。シート **Compare**（EN/JA File name, EN/JA Article title, Update, Summary, Match rate, Target translated date=JA git日, Current date=EN git日, Note）＋ **Data**。Update 区分: Identical / EN Updated / Not localized / Only Japanese / Not in C。

**TM**: 既定 `…\XTM\20260902\Domo_Domo University-en_US-ja_JP-…tmx`、索引キャッシュは `…\Kotonoha\Index\jaen_<指紋>.pkl`（初回~38秒/JAキー214,840）。

**実行結果（2026-09-15）**: Identical 894 / EN Updated 480 / Not localized 476 / Only Japanese 9。

**検証で判明**: 同記事の EN/JA は画像パス完全一致（言語非依存で信頼）だが、リンクはローカライズ差（EN `…/domo-central/university` ↔ JA `…/jp/domo-central/university`）。当初リンクも判定に使い EN Updated が 1076 件と過剰 → リンク除外で 480 に是正。

---

## 5. 残作業（明日以降・ユーザー合意済み）
1. **リンク比較の有効化**: 「`/jp/` は無視してOK」との指示。JA 側リンクから `/jp/`（末尾 `/jp`）を除去して正規化すればリンクも言語非依存マーカーとして使える。`ja_version_check.py` の `classify()` で extra_links を再度トリガーに戻し、比較前に正規化を追加する。※フォーラムは `…/main` ↔ `…/jp` のようにセグメント自体が異なるケースあり要確認。
2. **content-todo 480件の内容比較**: `JA_version-YYYYMMDD.content-todo.json` を Claude が内容比較 → done.jsonl → `--inject` で反映。件数が多いためバッチ的に。**着手前にユーザーと相談**。

## 6. 関連メモリ
- `ja-version-check-tool.md`（新規ツール仕様＋残作業）
- `file-comparison-tool.md`（EN比較ツール・Changed列/Data/__Results/EN_comp 等）
- `tm-match-explorer-tool.md`（TM索引方式・pandoc reference 運用）
