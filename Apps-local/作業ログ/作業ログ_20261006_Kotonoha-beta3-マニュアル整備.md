# 作業ログ 2026-10-06 — Kotonoha beta3 マニュアル整備（表紙・目次・章番号・変更履歴）

## 概要
Kotonoha beta3 の操作マニュアル（`CAT tool\CAT\Kotonoha-beta3\Kotonoha-beta3-マニュアル.md` / `.docx`）を整備。**表紙・目次の追加**、**章番号を 1 始まり**に変更、**第1章を「変更履歴」に再編**（バージョン別サブセクション＋日付入り表）。`.md` 原本を編集し pandoc で docx を再生成（「.md が原本・docx は生成物」方針を維持）。

関連の問い合わせ対応（File Comparison・TM 参照場所）も実施。

---

## 1. 問い合わせ対応（参考）
- **File Comparison**：`File-Comparison.bat` が起動する PS1 は同階層の `Run-FileComparison.ps1`。比較対象＝「Current 版の英語ソース（既定 `_________GitHub-Main\domo-documentation-hub\s\article`）」×「前回翻訳版の英語ソース（実行時指定→`s\article` 自動解決）」。出力名＝`File_Comparison[-ラベル]_<今日YYYYMMDD>-<前回版MMDD>.xlsx`（既定 `File comparison\__Results`）。
- **Kotonoha beta3 の TM 参照**：既定はハードコードだが解析系メニューで実行時に上書き可。これを機に beta3 でパス指定＋前回値記憶を強化（2026-09-28 実装分）。

---

## 2. マニュアル：表紙＋目次の追加
- `.md` 冒頭に **YAML フロントマター**（`title`/`subtitle`/`date`/`lang`）を追加＝**表紙**。重複する旧 H1 は置き換え。
- pandoc は **`--from gfm+yaml_metadata_block`**（gfm 既定は YAML を無視するため拡張必須）。
- **目次**＝`--toc --toc-depth=3`。
- 表紙と目次の間の**改ページ**＝`--include-before-body "_cover-pagebreak.openxml"`（中身は `<w:p><w:r><w:br w:type="page"/></w:r></w:p>`）。これで順序が **表紙 → 改ページ → 目次 → 本文**。
- pandoc の docx 目次は**空の Word フィールド**なので、**`pandoc-reference.docx` の `word/settings.xml` に `<w:updateFields w:val="true"/>` を注入**。pandoc が引き継ぎ、**Word 起動時に目次が自動更新**される。
  - 注意：生成 docx 側は `/>` の前に空白が入り `<w:updateFields w:val="true" />` となる（grep 時に注意）。

### 追加した資産
| ファイル | 役割 |
|---|---|
| `_cover-pagebreak.openxml` | 表紙→目次の改ページ（include-before-body 用） |
| `_build-manual-docx.bat` | マニュアル docx 再生成（pandoc 実行・CRLF） |
| `pandoc-reference.docx` | `settings.xml` に `updateFields` を注入（目次自動更新用） |

---

## 3. マニュアル：章番号を 1 始まりに
- 旧「0. beta1 からの変更点」始まりを **1 始まり** に全面リナンバー（0→1, 1→2, …, 8→9）。サブ章 `6a`/`6b` は `7a`/`7b` に。
- 本文中の相互参照も整合（`§7`→`§7a`、`§6b`→`§7b`）。beta1 マニュアルを指す `§5–§7` は別ドキュメント参照のため据え置き。

---

## 4. マニュアル：第1章を「変更履歴」に再編
- 大カテゴリー **`## 1. 変更履歴`** を新設し、バージョンごとのサブカテゴリー（`###`）に **日付｜修正内容** の表（罫線）で整理。
- 収録：
  - **beta1**（2026-09-09）初版：Pre-translation 化・新規全件 MT・3パス構成。
  - **beta2**（2026-09-11）高速化①②③＋TEP 確定の Live_TM 書き戻し ／（2026-09-14）マニュアル docx 化。
  - **beta3**（2026-09-28）TM・ドキュメントのパス指定＋前回値記憶・入力検証（再入力/キャンセル）・UI Glossary 作成 ／（2026-10-06）表紙・目次・章番号1始まり・変更履歴新設。
  - **RTM（予定）** テンプレート行（RTM1／RTM2… を今後追記）。
- 旧「①②③」説明は beta2 行に集約し、`※ 高速化①は出力不変／指紋＝パス＋サイズ＋更新日時` を注記として残置。

---

## 5. 検証
- docx 再生成（`--from gfm+yaml_metadata_block --reference-doc pandoc-reference.docx --toc --toc-depth=3 --include-before-body _cover-pagebreak.openxml`）exit 0。
- 構成順＝**表紙 → 改ページ → 目次 → 本文**、`updateFields=true`（Word で自動更新）を確認。
- 第1章「変更履歴」と beta1/beta2/beta3/RTM 各サブセクション、日付（09-09／09-11／09-28／10-06）すべて docx に反映。
- 旧「0. 章」が消滅し「9. 制約」まで 1 始まりで並ぶことを確認。

---

## 6. 今後の運用
- マニュアルは **`.md` を編集 → `_build-manual-docx.bat`** で docx 再生成（目次は Word で開くと自動更新。古い場合は目次を右クリック→フィールド更新／`F9`）。
- 新バージョンは「変更履歴」に `### <版>` セクションと `日付｜修正内容` 行を追加していく。

## 残タスク
- RTM 行は現在プレースホルダ（日付「—」）。正式版リリース時に記載。
- 必要に応じて変更履歴の日付を「日時（HH:MM）」粒度へ拡張可能。
