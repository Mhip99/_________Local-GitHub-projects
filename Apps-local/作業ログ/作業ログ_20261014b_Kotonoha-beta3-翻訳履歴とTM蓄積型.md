# 作業ログ 2026-10-14（その2） — Kotonoha beta3 翻訳履歴（TM蓄積型）＋TEP編集画面の履歴ペイン

## 概要
前段「全機能GUI化」に続き、ユーザー指定の**次段階**を実装。TM を「原文キーで1訳・上書き型」から「**過去訳を更新日時付きで蓄積（上書き・削除しない）**」へ変更し、TEP編集画面に**翻訳履歴ペイン**（左下）を追加。右側に**用語ペインの領域だけ**確保（機能は後日）。計画は承認済み（plan: `smooth-dreaming-pnueli.md`）。実装前に Explore 3本で索引・pre-translation・編集画面を精読。

## 設計（最小破壊）
`exact_target`（原文→訳1本）は互換維持しつつ意味を「**最新**訳」に変更。別フィールド `exact_hist`（原文→版リスト〔訳＋日時〕）を追加 → マッチ消費側（analysis/doc_export/ui_glossary）は無改修で最新訳を使い、履歴は `exact_hist` から供給。

## 変更ファイル
### `tm_index.py`
- `Index.__slots__` に `exact_hist` 追加。`_index_tmx` で各 `<tu>` の `changedate`（無ければ `creationdate`）を読み取り、`exact_hist[k]` に `{ja,date}` を蓄積（同一 ja は重複排除・最新 date 保持）。
- `build_index` 後段で**複数版キーのみ** `exact_target[k]` を最新 date の訳へ差し替え（newest-wins）。単一版キー（大多数）は従来どおり＝回帰なし。
- `FORMAT_VERSION` を `kotonoha-idx-2`→`kotonoha-idx-3` に bump（旧 `.pkl` 自動 STALE→再ビルド）。

### `tm_match_analysis.py`
- `idx.exact_hist` を受け、`hist_of(k)`（新しい順）を定義。`analyze()` の各行に `hist` を付与（完全一致=`hist_of(sn)`／あいまい=`hist_of(bestk)`／MT=`[]`）。pct/st/band/tm/ja ロジックは無改修。

### `tm_writeback.py`（蓄積型）
- `load_tmx`: 値を単一dict→**版リスト** `od[src]=[{tgt,prev,next,creationdate,changedate},...]`（既存TMXの同一原文の全TUを読む・同一tgtは重複排除）。
- `merge_into`: 上書き廃止。確定訳が**未収録なら新版を append**（`changedate=now`）、同一訳は日時のみ更新。集計を `(new N, same M)` 表記に。
- `write_tmx`: 原文ごとに**版リストを古→新順で複数 `<tu>`** 出力（各版が自分の `changedate`/`creationdate` を保持）。
- dry-run・（前段GUIの）本実行前自動バックアップはそのまま有効。

### `TM-Match-Explorer-demo.html`（兼テンプレート）
- 3領域レイアウト追加（CSS `.worklayout/.leftcol/.rightcol/.histpane` ＋ 狭幅980px以下は縦積み）: **中央=セグメント表／右=用語ペイン（プレースホルダ「後日実装」）／左下=履歴ペイン `#histpane`**。
- 行 `<tr>` に `data-i` 付与。`#rows` に**クリック委譲**追加（textarea/checkbox 操作は除外）→ 行選択ハイライト＋`renderHistory(i)`。
- `renderHistory`: `SEG[i].hist` を新しい順に「更新日時＋訳」で一覧（最新を強調）。履歴なしは案内文。`fmtDate` で `YYYYMMDDTHHMMSSZ`→`YYYY-MM-DD HH:MM`。原文は `plain(SEG[i].en)`。
- 既存の編集/確定/XLIFF/localStorage は無改修。デモSEGに履歴サンプルを2件付与（デモ単体でも挙動が見える）。
- 無改修: `doc_export.py` / `ui_glossary.py` / `projects.py`（`exact_target` が文字列=最新のまま）。

## 検証（E2E・隔離／scratch）
- **索引**: 同一原文2版（日時違い）TMX → `exact_target`=最新訳、`exact_hist`=2版。`FORMAT_VERSION` bump で再ビルド。
- **書き戻し蓄積**: scratch master に同一原文の異なる確定訳を2回書き戻し → TMX の `<tu>` が 0→1→2、**旧訳が消えず両方残存**、各 `changedate`。dry-run 件数表示。
- **生成（編集画面）**: 蓄積TMで `tm_match_analysis` 実行 → 生成HTMLの該当SEGが `st=tm/b=100%`・**採用 tm=最新訳**・`hist=[最新,旧]`（日時付き）。HTMLに `worklayout/histpane/termpane/renderHistory` を確認。
- **回帰**: 単一版TMX → 100%一致・tm訳・`hist`1件、MTは `hist=[]`。従来挙動不変。
- 全 `.py`（tm_index/tm_writeback/tm_match_analysis/projects/inject_mt/ui_glossary/doc_export）`py_compile` OK。実運用 Master TM には書かず scratch で検証。

## 追記: 実機ブラウザ確認＆マニュアル Rev 3.00（同日 2026-10-14）
- **実機ブラウザ確認 完了**: 隔離ストア＋蓄積TMでサーバーモード起動＋編集画面を開いて確認。履歴ペインの**レイアウトをユーザー指定で修正**＝「セグメント表を全幅」「履歴ペインは左下／用語ペインはその横（右下）」。`TM-Match-Explorer-demo.html` を `.worklayout`(表+右サイド) から **`.panerow`(表=全幅、下に histpane 左｜termpane 右、820px以下は縦積み)** へ変更し再生成で確認 → ユーザーOK。テストサーバー停止・隔離環境(`__testdata-1014\_demo`)削除・実台帳3件無傷。
- **マニュアル Rev 3.00 発行**: `.md` 原本を新規作成し pandoc で docx 生成。
  - 付番: ユーザー指定どおり 2.00→**3.00**（大機能追加＝整数部+1）。
  - 更新: メニューを現行化（**[1]/[2]廃止→[C]作成+実行・[D]サーバーモード・[P]→X出力**）、§4b サーバーモード(全機能GUI)・§4c 元形式で出力(多フォーマット)・§7c 翻訳履歴(TM蓄積型)と履歴ペイン を**新設**、§7a 書き戻しを**蓄積型**に改訂、構成に `doc_io.py`/`doc_export.py` 追加、§1.1/§1.2 履歴に 10/08・10/09・10/14 と Rev3.00 を追記。
  - 生成: `pandoc Rev3.00.md -f gfm+yaml_metadata_block -s --toc -o Rev3.00.docx --reference-doc <beta3同梱 pandoc-reference.docx>`。docx 30,657 bytes、タイトル/目次/新章を検証。旧 `_Rev2.00` は保存。

## 残タスク
- **用語ペインの中身（用語集機能）＝後日実装**（今回は領域確保のみ）。
- 既存 Live_TM（Master）は現状1TU/原文。今後の書き戻しから蓄積が始まる（既存データは次回書き戻し時に版リスト化）。
