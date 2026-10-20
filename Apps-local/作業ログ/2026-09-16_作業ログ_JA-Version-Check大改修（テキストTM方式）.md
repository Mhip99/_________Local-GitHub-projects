# 作業ログ 2026-09-16 — JA Version Check 大改修（テキスト/TM方式へ）

対象: `________GitHub-production\File comparison\JA_comp\`

昨日(2026-09-15)新規作成した **JA Version Check** の残作業から再開。最終的に、判定方式を**テキスト（TM）のみ**へ全面変更し、Pass2（Claude 内容比較）を廃止する方針まで確定した。以下は経緯と最終状態、明日の計画。

---

## 1. リンク比較の有効化 →（後に撤回）
- 当初残作業①として、`classify()` にリンク比較を復帰。`canon_link()`（article/topic の ID 化、`?language=` 除去、scheme/host 正規化、`/en-US` 等ロケール除去、forum `/main`↔`/jp` 統一、旧zendesk 対応）＋コード例除去を実装。EN Updated 480→686。
- パイロット等で検証後、**§6 の方針転換により URL・画像比較ごと撤回**（`markers()`/`canon_link()`/`jaccard()` は削除）。

## 2. マニュアル docx 上書き事故 と復旧
- `.md` 更新後に pandoc で docx を再生成した際、**ユーザーが直接編集していた docx（同日 12:54 版）を上書き消失**させた。
- ユーザーが `Downloads\JA-Version-Check-マニュアル (6).docx` を提供 → 内容を取り込み。
- **教訓**: マニュアルは `.md` が原本・docx は pandoc 生成物。**docx 再生成前に手動編集の有無（docx が .md より新しい等）を必ず確認**する。→ メモリ `manual-md-is-master` に記録。

## 3. 用語統一（ユーザーのマニュアル手直しを全ファイルへ反映）
- 未追随→**未更新** / 名前違い→**ファイル名が異なる** / 突き合わせ→**比較** / 追随しているか→**英語版と同じバージョンの日本語版が存在するか**。
- 節見出しを 1 起点に、§1「ツールの用途」、§4「内容の比較（EN↔JA のペアリング）」。
- `.md`/`.docx`・`ja_version_check.py`(docstring/help/comment)・`tm_ja_en.py`・`Run-JAVersionCheck.ps1` に反映（.ps1 は UTF-8 BOM 維持を確認）。→ メモリ `terminology-ja-doc-tools`。

## 4. パイロット（Pass2 並列ワークフロー・30件）
- content-todo を 5 件/チャンクに分割し、並列ワークフローで各サブエージェントが EN/JA 本文を比較 → `{en,update,summary,note}` を集約。30件・6エージェント・約77秒・45万トークン。
- 結果: Identical 18（ローカライズリンク/画像ロケール/目次追加等の偽陽性）、本物 EN Updated 6、**別記事/スタブ6**。
- 仕様追加: `BODY_LIMIT=20000`（本文上限、旧8000）、**Mismatch** ラベル（同コード名で別記事。色=赤、Pass2 でのみ付与）、`--inject` の色再適用。
- ※この後の方式変更により、パイロット成果物は参考外に。

## 5. 【本日の主変更】判定方式をテキスト/TM のみに全面変更
ユーザー指示: **URL と画像の比較を仕様から除外。内容比較はテキストボディーのみ。日付・見出し数も比較対象外。**

確定した新仕様:
- **対応付け**: ①ファイル名（コード）一致 → ②Title 一致（EN title を **TM で JA に訳し** JA title と一致比較）→ ③内容（TM(JA→EN) で JA 本文→英語原文を引き EN 本文照合）。画像 jaccard 対応付けは廃止（空集合 jaccard=1.0 で無画像同士が偽 100% になるバグも解消）。
- **Match rate = TM カバレッジ率**: EN 本文を文単位で **TM(EN→JA)** 参照 → その訳文が JA 本文に含まれる割合(%)。TM 訳の無い文は分母除外、皆無は空欄。
- **Update**: Match rate ≥ しきい値 → Identical、未満/判定不能 → EN Updated。**日付・画像・URL・見出しは判定不使用**（git 日付は参考列として残置）。
- **TM モジュール刷新**: `tm_ja_en.py` を **JA⇄EN 双方向**化（`FORMAT_VERSION=jaen-enja-2`、cache=`tmidx_<fp>.pkl`、JA 214,840/EN 187,257 キー）。カバレッジは `lookup_en2ja_exact`（exact のみ）で高速化（fuzzy は候補膨大で遅く実用不可だった）。

実測(しきい値75%時): Identical 895 / EN Updated 473 / Not localized 482 / Only Japanese 15。
Match rate 分布(1368ペア): 100%=318, 90-99=155, 75-89=422, 50-74=254, 25-49=79, 0-24=56, 判定不能84, 中央値83.3%。

## 6. しきい値と Pass2 の扱い（最終方針）
- 検証で判明した**重大な性質**: Match rate は「TM 訳がそのまま JA 本文に含まれる割合」のため、**後編集された訳は字面が変わり不一致扱い＝実質最新でも 75〜85% に留まる**。→ しきい値 75% だと本物の EN Updated（レポート行の欠落等）を Identical に取りこぼす（false negative）ことを実データで確認（000005441/000005535/000005254/000005095 など）。
- ユーザー判断: **しきい値は 99%**（`--pass2-threshold` 既定を 99.0 に変更）。ほぼ完全一致のみ Identical、それ以外は EN Updated。
- ユーザー判断: **「EN Updated には Pass2 不要（差分が多く再翻訳するから）」** → **Pass2（Claude 内容比較）を廃止**。Identical も EN Updated も Claude 確認は不要なので、**ツールは Pass1（Match rate）のみで完結**。並列ワークフロー・content-todo・判定キャッシュ計画はすべて撤回。

## 7. ファイル整理
- `__Results\JA version` の旧成果物を削除（09-15 の content-todo/xlsx、無印・-01 の xlsx、pilot 一式）。現行は `JA_version-20260916-02.xlsx` と `content-todo.json` のみ（※明日 Pass1 再実行で刷新予定）。
- 旧 TM キャッシュ `jaen_<fp>.pkl`（未使用）は TM 管理フォルダ内のため未削除（削除可）。

---

## 8. 残作業（明日 2026-09-17・ユーザー合意済）
1. **★ Match rate を「あいまい一致」方式へ改良（最優先）**: 現行の exact 部分一致は後編集訳を過小評価するため、EN 各文の TM 訳を JA 本文の文集合とトライグラム類似度で照合し閾値以上を「カバー済」と数える方式に。JA 本文を文集合に前処理して速度確保。→ EN Updated の誤検出（実質最新なのに<99%）を大幅減。Pass2 廃止で Match rate 単独判定になるため精度が要。
2. **ツールを Pass1 のみに整理**（`--inject`/Pass3・content-todo 生成を不要化）。
3. **99% しきい値で Pass1 再実行** → 再翻訳対象（EN Updated）リスト確定。
4. **Mismatch ラベルの要否決定**（廃止／極低 Match rate で自動付与／現状維持）。
5. **マニュアル・メモリの Pass2 記述を全面削除**（現状 Pass2 前提の記述が残存）。しきい値 99% の数値反映は済。

## 9. 関連メモリ
- `ja-version-check-tool`（現行仕様＋明日の計画）
- `terminology-ja-doc-tools`（日本語用語の統一表記）
- `manual-md-is-master`（マニュアルは .md 原本・docx 上書き注意）
