# JA Version Check — マニュアル

**最新フォルダの日本語版が英語版と同じバージョンかをチェック**するツールです。
英語版が更新された後、そのバージョンの日本語版翻訳が作成されているか否かをチェックし、「最新版に更新済み」「日本語版が古いバージョンのまま（未更新＝要再翻訳）」「未ローカライズ」「英語版がなく日本語記事のみ存在」などの結果を Excel 形式でレポートします。

> 場所: `OneDrive - Domo Inc\________GitHub-production\File comparison\JA_comp\`

---

## 1. ツールの用途

1. **Current EN と JA の照合**: 英語版(EN)と日本語版(JA)の記事を比較し、英語版と同じバージョンの日本語版が存在するか（日本語版翻訳後に英語版が更新されていないか）を判定。
2. **日本語版のみ／英語版のみの抽出**: 対応する英語版が無い日本語版（Only Japanese）、日本語版が無い英語版（Not localized）を抽出。Published Japanese version のパスを与えると、それも比較対象に含めます。

対象フォルダー（既定）:
- 英語版(EN): `…\_________GitHub-Main\domo-documentation-hub\s\article`
- 日本語版(JA): `…\_________GitHub-Main\domo-documentation-hub\ja\s\article`

> **比較方針**: 対応付け・Match rate・判定は**テキスト本文（TM 経由）のみ**で行います。**URL・画像・日付・見出し数は使いません**（日付は Excel に参考表示するだけ）。判定は実行1回（Pass1）で完結し、Claude による内容比較パスはありません。

---

## 2. 構成ファイル

| ファイル | 役割 |
|---|---|
| `JA-Version-Check.bat` | **ダブルクリック起動用**バッチ |
| `Run-JAVersionCheck.ps1` | ランチャー（説明表示→実行確認→Published パス入力→実行） |
| `ja_version_check.py` | **本体エンジン** |
| `tm_ja_en.py` | TM(JA⇄EN 双方向)索引モジュール（EN→JA=訳文参照, JA→EN=原文参照。pickleキャッシュ） |
| `JA-Version-Check-マニュアル.md` / `.docx` | 本マニュアル |

**動作要件**: Python 3.11 ＋ `openpyxl`、**git**（コミット日時取得。PATH または既定インストール先を自動解決。※日付は参考表示のみで判定不使用）、TM の TMX（JA⇄EN）。

---

## 3. 使い方

### 起動（推奨: バッチをダブルクリック）
`JA-Version-Check.bat` をダブルクリック → 説明が表示され、**実行するか(Y/N)** を確認 → **Published Japanese version フォルダー**のパスを尋ねられます（無ければ Enter でスキップ）→ 実行。

PowerShell から:
```powershell
.\Run-JAVersionCheck.ps1
# 例: Published 版も比較
.\Run-JAVersionCheck.ps1 -Published "C:\...\published-ja"
```

実行すると `__Results\JA version\JA_version-YYYYMMDD.xlsx` が出力され、それが最終結果です（追加パスなし）。**EN Updated の行が再翻訳対象**です。

| 引数(ランチャー / エンジン) | 説明 |
|---|---|
| `-En` / `--en` | 英語版フォルダー（既定あり） |
| `-Ja` / `--ja` | 日本語版フォルダー（既定あり） |
| `-Published` / `--published` | Published Japanese version フォルダー（任意） |
| `-Results` / `--results` | 出力フォルダー（既定 `__Results\JA version`） |
| `--identical-min` | Match rate がこの値以上を Identical、未満を EN Updated（既定 99） |
| `--cover-sim` | Match rate 算出のカバー判定に使う文トライグラム類似度しきい値（既定 0.6） |
| `-NoTM` / `--no-tm` | TM 参照を使わない（Match rate 算出・TM 対応付け不可） |

---

## 4. 対応付けと Match rate

### 対応付け（EN↔JA のペアリング）
日本語版のソースである英語版を、次の優先順で対応付けます（**テキストのみ。画像・URL・日付は不使用**）。

1. **ファイル名（コード名）が一致** → 対応確定。
2. **Title が一致**: EN の title を **TM で日本語に訳し**、JA の title と一致（正規化一致／包含／高類似）すれば対応確定。
3. **内容（TM）で対応**: 上記どちらでもない JA について、日本語本文を **TM(JA→EN)** で英語原文に引き、その英文を含む EN ファイルを探して対応付け（Note に「内容照合(TM原文)」）。
4. どれでも対応が付かない → **Only Japanese**（JA のみ）/ **Not localized**（EN のみ）。

### Match rate（TM カバレッジ率）
すべての対応ペアについて、**EN 本文を文単位で TM(EN→JA) 参照 → その訳文が JA 本文でカバーされるか**を判定し、**カバーされた割合（%）を Match rate** とします（＝EN 内容の JA カバレッジ率）。

- カバー判定は「JA 本文に**そのまま含まれる**（完全一致）」または「**JA いずれかの文とトライグラム類似度 ≥ `--cover-sim`（既定0.6）**」。後者により、後編集で字面が変わった訳も拾えます。
- TM に訳が無い EN 文は分母から除外。対象文が皆無なら空欄（判定不能）。

> **性質（重要）**: Match rate は TM 訳と JA 本文の**字面の重なり**に基づく近似値です。あいまい一致により後編集訳もかなり拾えますが、**大幅な言い換え・意訳や TM 未収載の文が多いと低めに出ます**。したがって Match rate は「一致度の目安」であり、厳密な内容一致率ではありません。

---

## 5. Update 区分（判定結果）

| 値 | 意味 | 色 |
|---|---|---|
| **Identical** | Match rate が `--identical-min`（既定 99%）以上。EN 内容は JA にほぼ反映済み | 緑 |
| **EN Updated** | Match rate が既定 99% 未満（判定不能含む）。EN に JA 未反映の内容がある＝**要再翻訳** | オレンジ |
| **Not localized** | 日本語版が存在しない（英語版のみ） | 黄 |
| **Only Japanese** | 英語版が存在しない（日本語版のみ） | 青 |
| **Not in C** | Current 版に存在しない（Published JA 比較時） | グレー |

**判定は Match rate（TM カバレッジ）のみ**で行います。日付・画像・URL・見出し数は使いません。EN Updated は差分があるため**一律再翻訳**の運用です（Claude による内容確認パスは行いません）。

> 「同コード名だが別記事」の自動判定（Mismatch）は設けていません。TM 未収載の同一記事（短いチャート記事など）を誤検出するため信頼できないためです。そうしたケースは Match rate が低い **EN Updated** として現れ、真に別記事の場合の多くは対応が付かず **Not localized / Only Japanese** に出ます。

> しきい値 99% は「ほぼ完全一致のみ Identical」とする設定で、小さな欠落（レポート行の追加漏れ等）も見逃さない代わりに、後編集で字面が変わった実質最新も EN Updated に含まれ得ます（＝再翻訳対象がやや多め）。`--identical-min` で調整できます。

---

## 6. 出力 Excel

出力: `__Results\JA version\JA_version-YYYYMMDD.xlsx`（`YYYYMMDD`＝作成日）。
**最新版は常に番号なし**（`JA_version-YYYYMMDD.xlsx`）。再実行するたびに、それまでの最新版を**古い順に `-01`, `-02` … へ退避**して番号なしを最新用に空けます（**旧版は削除せず常に残す**）。したがって `-01` が最も古く、番号なしが最新です。

### シート「Compare」列
| 列 | 内容 |
|---|---|
| EN File name | 英語版ファイル名 |
| JA File name | 日本語版ファイル名 |
| EN Article title | 英語版タイトル |
| JA Article title | 日本語版タイトル |
| Update | 判定（§5） |
| Summary | 判定の根拠（Match rate 等） |
| Match rate | TM カバレッジ率%（§4）。判定不能は空欄 |
| Target translated date | 日本語版の更新日（git コミット日・**参考表示のみ／判定不使用**） |
| Current date | 英語版の更新日（git コミット日・**参考表示のみ／判定不使用**） |
| Note | 補足（Title一致/内容照合(TM原文) 等） |

並び順: EN Updated → Not localized → Only Japanese → Not in C → Identical。色分け・オートフィルター・ヘッダー固定・罫線つき。

### シート「Data」
Item / Note の2列。English version folder / Current Japanese version folder / Published Japanese version folder / Work date/time を記録。
さらに **Update counts** として、Update 各区分（Identical / EN Updated / Not localized / Only Japanese / Not in C）の件数と **Total**（＝Compare シートの行数）を記載します。

---

## 7. TM（JA⇄EN 双方向）

- 既定 TMX: `…\XTM\20260902\Domo_Domo University-en_US-ja_JP-2026-09-02.tmx`（`--tmx` で変更可）。
- 索引は **Kotonoha の索引フォルダー**（`…\Kotonoha\Index`）に `tmidx_<指紋>.pkl` としてキャッシュ。初回のみ数十秒、以降は再利用。
- **EN→JA**（英文→訳文）: Match rate（カバレッジ）と Title 一致の判定に使用。
- **JA→EN**（和文→原文）: ファイル名が異なる記事の内容照合（対応付け③）に使用。
- `--no-tm` で無効化できます（無効時は Match rate 算出・TM 対応付けができません）。

---

## 8. 制約・注意点

- 比較は**テキスト本文（TM 経由）のみ**。**日付・画像・URL・見出し数は判定に使いません**（日付は参考表示）。
- **Match rate は近似値**（TM 訳と JA 本文の字面の重なり）。あいまい一致で後編集訳も拾うが、大幅な意訳・TM 未収載が多いと低めに出る。EN Updated は「要再翻訳」の目安として運用。
- しきい値は `--identical-min`（Identical 境界）・`--cover-sim`（カバー判定の文類似度）で調整可能。
- Pass1 は TM 索引がキャッシュ済みなら数秒〜十数秒で完了。2 回目以降の差分確認も高速。
- 出力先が無い場合はパス入力を求め、ロック時は時刻付き別名で保存します（File comparison と同様）。
