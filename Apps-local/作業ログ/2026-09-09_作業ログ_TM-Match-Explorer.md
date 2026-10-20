# 作業ログ — 2026-09-09 (TM Match Explorer / Kotonoha)

対象: `OneDrive - Domo Inc\________GitHub-production\CAT tool\CAT\`（HTML版 CAT ツール）

---

## 本日のゴール
ユーザーの翻訳プロセス（`TM分析 → Pre-translation → 作業者がTEP → 納品訳`）に合わせて CAT ツールを改修し、DomoStats Connector で Pre-translation（新規全件 MT 含む）を生成。その後、実行ファイルを `Kotonoha\` に集約し、起動バッチを作成。

---

## 1. 現状ツールの実行・確認
- 既存 `tm_match_analysis.py` を University TMX(395MB) で実行し現状を確認。
- **問題発見**: 旧版は納品訳を入力(`--translation`)として TM訳との差分を表示していたが、プロセス上 **納品訳は下流の成果物**（分析時点では未存在）。ソース1,703 vs 納品訳1,395 の行ズレの原因でもあった。

## 2. 設計変更（ユーザー確認済み）
- `--translation`（納品訳）を **廃止**。行ズレ問題も解消。
- Japanese 列 = **Pre-translation**：`>=75%` は TM 訳を流し込み(`st:"tm"`)、`<=74%`（新規）は **MT（Claude の AI 翻訳、`st:"mt"`）**。
- マッチTM = **University（主）＋ Product（UI追加マッチ＋MT用語ヒント）**。
- 今回の作業範囲 = ツール改修 ＋ DomoStats 全 MT 実行。

## 3. コード改修
- **`tm_match_analysis.py`**（改修）: `--translation` 削除、`--product-tmx` 追加。University→Product の順で索引、重複キーは EN 4 語以下なら Product 優先。Product 用語集(glossary)を stopword/長さフィルタ(`term_ok`)付きで抽出し `mt-todo.json` に添付。行スキーマに `st` 追加。
- **`inject_mt.py`**（新規）: `mt-done.jsonl` を読み HTML の `const SEG` に MT を注入（TMX 不要・高速）。
- **`TM-Match-Explorer-demo.html`**（テンプレート）: SEG に `st` 追加、**MT バッジ**表示、見出し「Japanese (Pre-translation)」、XLIFF を `st`＋編集状態で `state`/`state-qualifier`（exact-match / fuzzy-match / mt-suggestion）に分岐。`<note>` の XML エスケープ漏れも修正。

## 4. DomoStats の Pre-translation 生成（全 MT）
- 入力: source `Analysis and Translation\Sample\ED2708-03-…\1_en\360043433813.mdx` × University+Product TMX（2026-08-25）。
- 結果: 全 **1,703** セグメント = TM 流し込み **612**（ICE 5 / 100% 176 / 95-99 36 / 85-94 243 / 75-84 152）＋ **MT 1,091**。
- MT 1,091 件を Claude が全訳（バッチ処理で `mt-done.jsonl` へ、欠落 0 / 余分 0 を検証）し、`inject_mt.py` で注入。
- 成果物: **`TM-Match-Explorer-DomoStats-PreTrans-20260909.html`**（0.46MB）＋ `.mt-todo.json` / `.mt-done.jsonl`。
- 旧スキーマの中間 HTML（初回実行分）は削除。

## 5. ファイル移動（Kotonoha 集約）
- 実行ファイル 3 点を `CAT\Kotonoha\` に移動: `tm_match_analysis.py` / `inject_mt.py` / `TM-Match-Explorer-demo.html`。
- 生成物・ドキュメント（demo.md, prompt/, PreTrans HTML, mt-*）は `CAT\` 直下に残置。旧 `__pycache__` 削除。
- Kotonoha からの実行（Pass1 構文 / Pass3 実動）を確認済み。

## 6. 起動バッチ作成
- **`Kotonoha\TM-Match-Explorer.bat`**（メニュー式ランチャー）を作成。
  - [1] 解析＋Pre-translation（Pass1） / [2] MT 注入（Pass3） / [3] テンプレートプレビュー / [Q] 終了。
  - 自フォルダに cd、Python 存在チェック、TMX 既定値（Enter で採用）、Product 空欄可、`chcp 65001`。
  - ※ 中間の MT は Claude が担当するため 1 バッチでの全自動完結は不可（Pass1/Pass3/プレビューをバッチが担当）。

## 7. ドキュメント・メモリ更新
- `TM-Match-Explorer-demo.md`（新フロー・3パス・Kotonoha の場所注記）、`prompt/TM-Match-Analysis.md`（冒頭に現行フロー注記・旧 docx はレガシー）を更新。
- メモリ `tm-match-explorer-tool.md` を新規作成し `MEMORY.md` に登録。

---

## 成果物一覧
| ファイル | 場所 | 備考 |
|---|---|---|
| `tm_match_analysis.py` | `CAT\Kotonoha\` | 解析＋Pre-translation エンジン（改修） |
| `inject_mt.py` | `CAT\Kotonoha\` | MT 注入（新規） |
| `TM-Match-Explorer-demo.html` | `CAT\Kotonoha\` | UI テンプレート（改修） |
| `TM-Match-Explorer.bat` | `CAT\Kotonoha\` | 起動ランチャー（新規） |
| `TM-Match-Explorer-DomoStats-PreTrans-20260909.html` | `CAT\` | Pre-translation 完成版（全 MT 注入済） |
| `….mt-todo.json` / `….mt-done.jsonl` | `CAT\` | MT 対象リスト / 翻訳結果ログ |

## 残課題・留意
- ソースが散文主体のため Product 追加でも MT 件数はほぼ不変（Product の主効果は用語統一）。
- MT は下訳（TEP 前提）。類似度は文字ベースのため XTM 実測と差あり。
- セグメント分割は SRX 非完全再現。将来の拡張候補: SRX 準拠分割、MT 品質向上。
- バッチはダブルクリック利用前提（対話メニューの自動テストは未実施、Python 呼び出しは検証済み）。
