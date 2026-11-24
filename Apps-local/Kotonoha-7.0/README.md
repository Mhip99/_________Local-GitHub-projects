# Kotonoha 7.0 — TM Match Explorer（準備・セットアップ）

Domo ドキュメント翻訳用の CAT ツール（TMマッチ → Pre-translation → ブラウザで TEP → TM書き戻し）。**ローカル専用**（`127.0.0.1`）で、機密は原則として外部へ送信しません。本書は別マシンでの導入手順です（マニュアル「第1章 準備編」と同一内容）。

## 1. 必要環境
- Windows ＋ **Python 3.x**（`python` が PATH に通っていること）。
- （任意）**LanguageTool**：英語のリアルタイム文法チェックを使う場合に必要（`_install-LanguageTool.bat` で自動導入）。
- （任意）**pandoc**：マニュアル docx を再生成する場合のみ。

## 2. 入手
- リポジトリを取得（clone / fetch）：`github.com/Mhip99/_________Local-GitHub-projects`。
- 本ツール本体＝`Apps-local\Kotonoha-7.0\`。

## 3. パス設定（マシンごと・任意）
- 索引キャッシュや LanguageTool の場所を既定から変える場合、`_kotonoha-paths.bat.sample` を **`_kotonoha-paths.bat`** にコピーし、`set "CACHE=…"`（索引キャッシュ）/ `set "LTDIR=…"`（LanguageTool）を設定（このファイルは **Git管理外**＝マシン固有）。
- 未設定時の既定：索引キャッシュ＝`Kotonoha-7.0\_Index`（初回自動作成）、LanguageTool＝`%LOCALAPPDATA%\Kotonoha-LT`。

## 4. TM データの配置（重要）
- TM（XTM の TMX 等・数百MB）は**リポジトリに含まれていません**。各自で TMX を配置し、プロジェクト作成時にそのパスを指定します。**TM が無いと解析・TMタブ・Concordance は動きません**（UI の起動自体は可能）。

## 5. 起動
- **`起動_Kotonoha-ハブ.bat`** をダブルクリック → ブラウザで `http://127.0.0.1:8765/`。
- 黒いコンソール窓を**閉じると停止**します（LanguageTool も同時停止）。
- 推奨ブラウザ：**Edge**、または拡張機能（Dark Reader 等）を `127.0.0.1` で無効化した Chrome（拡張が CSS を剥がすと表示が崩れます）。

## 6. プロジェクト作成・実行
- 「プロジェクト」タブ（またはランチャー `[C]`）で、ソース（.json / .mdx / フォルダ）・メインTM・Product/サブTM を指定して作成 → 実行（再解析）。
- 生成された記事タブ（**TEPタブ**）でレビュー・確定 → **「TEP完了」**（確定訳を由来TMへ書き戻し）／**「出力」**（翻訳版を元形式で書き出し。`2_For review` 上書き注意→ `3_Final`/任意推奨）。

## 7. （任意）英語リアルタイム文法（LanguageTool）
- **`_install-LanguageTool.bat`** を一度実行（ポータブル JRE ＋ LanguageTool を `%LOCALAPPDATA%\Kotonoha-LT` へ自動ダウンロード・展開／約290MB）。
- 以後、起動bat が LanguageTool サーバー（`127.0.0.1:8081`）を自動起動。操作行 **「スペル・文法チェック」ON** で、英語はリアルタイム下部パネル、日本語は Claude 半自動点検（いずれも外部送信なし）。

## 8. （任意）マニュアル docx 再生成
- pandoc 導入後、`_build-manual-docx.bat`。マニュアル原本は `Kotonoha-マニュアル_Rev7.0.md`（docx は生成物）。

## セキュリティ・注意
- ローカル専用・`/api/*` はトークン必須・Host 検証（DNSリバインディング遮断）・描画は未信頼データ（TM/MT/Claude/LanguageTool 出力）を常に `esc()`。詳細はマニュアル **§12 セキュリティ**。
- 機密（Domo）コンテンツを含むため、リポジトリの共有は**社内の情報管理ルールの範囲**で行ってください。
- 外部送信されるのは MT／日本語チェックの **Claude 点検**のみ（既存運用と同様）。LanguageTool・フォント・内蔵スペル（基本）は外部送信しません。
