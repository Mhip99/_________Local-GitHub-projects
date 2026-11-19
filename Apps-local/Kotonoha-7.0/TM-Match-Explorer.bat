@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"
title TM Match Explorer - Kotonoha beta6

set "SCRIPT=%~dp0tm_match_analysis.py"
set "INJECT=%~dp0inject_mt.py"
set "INDEXER=%~dp0tm_index.py"
set "WRITEBACK=%~dp0tm_writeback.py"
set "GLOSSARY=%~dp0ui_glossary.py"
set "PROJECTS=%~dp0projects.py"
set "TPL=%~dp0TM-Match-Explorer-demo.html"
set "OUTDIR=%~dp0.."
set "CFG=%~dp0_paths.cfg"

rem ================= 既定パス (初回のみ使用。以後は _paths.cfg の前回値を既定表示) =================
set "XTM=C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\XTM\20260902"
set "UNIV=%XTM%\Domo_Domo University-en_US-ja_JP-2026-09-02.tmx"
set "PROD=%XTM%\Domo_Domo Product-en_US-ja_JP-2026-09-02.tmx"
set "CACHE=C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\Kotonoha\Index"
set "LIVETM=C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\Kotonoha\Live_TM"
set "MASTER=%LIVETM%\Domo_Domo-Master.tmx"
set "PROJTM="
set "SRC="
set "SDIR="
set "OUT=%OUTDIR%\TM-Match-Explorer-Output.html"
set "ODIR=%OUTDIR%\Kotonoha-out"
set "XF="
set "XD="
set "GSRC="
set "GHTML="
set "GXLIFF="
set "GOUT=%OUTDIR%\UI-Glossary"

rem === 前回値があれば読み込んで既定を上書き ===
if exist "%CFG%" for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%CFG%") do set "%%A=%%B"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python が見つかりません。Python をインストールし、PATH を通してください。
  pause & exit /b 1
)

:menu
cls
echo ==================================================
echo    TM Match Explorer  (Kotonoha beta6)
echo ==================================================
echo   [C] プロジェクト作成+実行  解析+Pre-translation (単一記事/フォルダー) ★
echo   [P] 過去のプロジェクト     一覧から再開 / 保存した定義を実行(G)
echo   [D] ダッシュボードを開く   ブラウザで作成・実行 (ローカルサーバー) ★
echo --------------------------------------------------
echo   [3] MT を HTML に注入        単一
echo   [4] MT を HTML に注入        一括(combined)
echo   [5] 索引キャッシュを事前作成 (初回のみ数分)
echo   [6] UI テンプレートをブラウザで開く (プレビュー)
echo   [7] TEP 結果を TM に書き戻す (確定行のみ)
echo   [8] パス設定を表示 / 変更 (TM・ドキュメント)
echo   [9] UI Glossary を作成 (作業内容から UI 用語抽出)
echo   [Q] 終了
echo --------------------------------------------------
echo  解析+Pre-translation は [C]/[P] に一本化しました（旧 [1]/[2]）。
echo  単一記事はソースにファイルを1つ、フォルダー一括はフォルダーを追加。
echo  入力の実在を確認し、未検出時は 再入力(R)/キャンセル(C)=一つ前へ。
echo --------------------------------------------------
set "CHOICE="
set /p "CHOICE=番号を入力してください: "
if /i "%CHOICE%"=="C" goto newproj
if /i "%CHOICE%"=="D" goto dashserve
if "%CHOICE%"=="1" goto moved12
if "%CHOICE%"=="2" goto moved12
if /i "%CHOICE%"=="3" goto pass3
if /i "%CHOICE%"=="4" goto injbatch
if /i "%CHOICE%"=="5" goto prebuild
if /i "%CHOICE%"=="6" goto preview
if /i "%CHOICE%"=="7" goto writeback
if /i "%CHOICE%"=="8" goto settings
if /i "%CHOICE%"=="9" goto glossary
if /i "%CHOICE%"=="P" goto projects
if /i "%CHOICE%"=="Q" exit /b 0
echo.
echo  ※ 無効な入力です: "%CHOICE%"
choice /c RQ /n /m "  再入力(R) / 終了(Q): "
if errorlevel 2 exit /b 0
goto menu

:moved12
echo.
echo  ※ [1]/[2]（解析+Pre-translation）は [C] プロジェクト作成+実行 に統合されました。
echo     単一記事＝ソースにファイルを1つ追加、フォルダー一括＝フォルダーを追加して実行します。
echo.
choice /c CM /n /m "  C=プロジェクト作成+実行へ / M=メニューへ: "
if errorlevel 2 goto menu
goto newproj

:dashserve
echo.
echo === ダッシュボードをブラウザで開く（作成・実行が可能） ===
echo  ローカルサーバーを起動し、ブラウザが自動で開きます。
echo  「＋ 新規作成」でソース/TMを選んで作成・実行、各定義行の「実行」も使えます。
echo  このウィンドウはサーバー実行中です。終了するには Ctrl+C を押してください。
echo.
python "%PROJECTS%" serve --cache-dir "%CACHE%" --template "%TPL%" --engine "%SCRIPT%"
echo.
echo  サーバーを終了しました。メニューに戻ります。
pause & goto menu

:pass3
echo.
echo === [3] MT を HTML に注入 (単一) ===
:pass3_html
call :ask HTMLF FILE "[C]/[P] で生成した HTML"
if defined CANCEL goto menu
:pass3_mt
call :ask MTF FILE "mt-done.jsonl"
if defined CANCEL goto pass3_html
echo.
python "%INJECT%" --html "%HTMLF%" --mt "%MTF%"
echo.
echo 完了。HTML をブラウザで開いて TEP してください。
echo.
pause & goto menu

:injbatch
echo.
echo === [4] MT を一括注入 (combined / batch) ===
set "CTX=%ODIR%\combined.mt-todo.json"
:injbatch_ct
call :ask CTX FILE "combined.mt-todo.json"
if defined CANCEL goto menu
:injbatch_cm
call :ask CM FILE "combined.mt-done.jsonl"
if defined CANCEL goto injbatch_ct
echo.
python "%INJECT%" --combined-todo "%CTX%" --combined-mt "%CM%"
echo.
echo 完了。各記事の HTML に注入されました。
echo.
pause & goto menu

:prebuild
echo.
echo === 索引キャッシュの事前作成 ===
:prebuild_univ
call :ask UNIV FILE "University TMX"
if defined CANCEL goto menu
:prebuild_prod
call :ask PROD FILEOPT "Product TMX (使わない場合は -)"
if defined CANCEL goto prebuild_univ
:prebuild_cache
call :ask CACHE TEXT "索引キャッシュ フォルダー"
if defined CANCEL goto prebuild_prod
call :save
echo.
echo 実行中... (数分かかります)
if defined PROD (
  python "%INDEXER%" --tmx "%UNIV%" --product-tmx "%PROD%" --cache-dir "%CACHE%"
) else (
  python "%INDEXER%" --tmx "%UNIV%" --cache-dir "%CACHE%"
)
echo.
echo 完了。以後の [C]/[P] 実行はこのキャッシュを数秒で読み込みます。
echo.
pause & goto menu

:writeback
echo.
echo === TEP 結果を TM に書き戻す (確定行のみ) ===
echo  ブラウザで「確定」にチェックした行だけが書き戻されます。
:wb_xliff
echo  --- 読み込み XLIFF (ファイル or フォルダー) ---
call :ask XF FILEOPT "XLIFF ファイル (フォルダー一括なら -)"
if defined CANCEL goto menu
if defined XF (set "XD=" & goto wb_master)
call :ask XD DIROPT "XLIFF フォルダー"
if defined CANCEL goto wb_xliff
if defined XD goto wb_master
echo  ※ XLIFF が未指定です。
choice /c RC /n /m "  再入力(R) / キャンセル(C): "
if errorlevel 2 goto menu
goto wb_xliff
:wb_master
echo  --- 書き込み先 TM (パス＋ファイル名) ---
call :ask MASTER TEXT "Master TM"
if defined CANCEL goto wb_xliff
:wb_projtm
call :ask PROJTM TEXTOPT "Project TM (Master のみは -)"
if defined CANCEL goto wb_master
:wb_confirm
set "WARGS=--master "%MASTER%""
if defined XF set "WARGS=--xliff "%XF%" !WARGS!"
if defined XD set "WARGS=--xliff-dir "%XD%" !WARGS!"
if defined PROJTM set "WARGS=!WARGS! --project-tmx "%PROJTM%""
echo.
echo --- まず dry-run で確認 ---
python "%WRITEBACK%" !WARGS! --dry-run
echo.
choice /c YN /n /m "この内容で書き戻しますか? (Y=実行 / N=一つ前に戻る): "
if errorlevel 2 goto wb_projtm
python "%WRITEBACK%" !WARGS!
echo.
echo 完了。TM を更新しました。
echo.
pause & goto menu

:settings
echo.
echo === パス設定 (現在値) ===
echo  [読込] ソース .mdx     : !SRC!
echo  [読込] ソースフォルダー : !SDIR!
echo  [読込] University TMX  : !UNIV!
echo  [読込] Product TMX     : !PROD!
echo  [索引] Index キャッシュ : !CACHE!
echo  [出力] HTML (単一)      : !OUT!
echo  [出力] フォルダー(一括) : !ODIR!
echo  [書込] Master TM       : !MASTER!
echo  [書込] Project TM      : !PROJTM!
echo  設定ファイル           : %CFG%
echo --------------------------------------------------
:settings_confirm
choice /c YN /n /m "変更しますか? (Y/N): "
if errorlevel 2 goto menu
echo  (Enter=据置 / 変更する項目だけ入力。無効時は R/C、キャンセルで一つ前へ)
:settings_src
call :ask SRC FILEOPT "ソース .mdx (無しは -)"
if defined CANCEL goto settings_confirm
:settings_sdir
call :ask SDIR DIROPT "ソースフォルダー (無しは -)"
if defined CANCEL goto settings_src
:settings_univ
call :ask UNIV FILE "University TMX"
if defined CANCEL goto settings_sdir
:settings_prod
call :ask PROD FILEOPT "Product TMX (無しは -)"
if defined CANCEL goto settings_univ
:settings_cache
call :ask CACHE TEXT "索引キャッシュ フォルダー"
if defined CANCEL goto settings_prod
:settings_out
call :ask OUT TEXT "出力 HTML (単一)"
if defined CANCEL goto settings_cache
:settings_odir
call :ask ODIR TEXT "出力フォルダー (一括)"
if defined CANCEL goto settings_out
:settings_master
call :ask MASTER TEXT "Master TM"
if defined CANCEL goto settings_odir
:settings_projtm
call :ask PROJTM TEXTOPT "Project TM (Master のみは -)"
if defined CANCEL goto settings_master
call :save
echo.
echo 保存しました。
echo.
pause & goto menu

:glossary
echo.
echo === UI Glossary 作成 (作業内容から UI 用語・コマンド・メッセージを抽出) ===
echo  使う入力だけ指定 (不要な項目は - で空に)。1つ以上必要。
:gl_src
call :ask GSRC FILEOPT "ソース .mdx (UI markup 抽出)"
if defined CANCEL goto menu
:gl_html
call :ask GHTML FILEOPT "生成/TEP HTML (EN->JA セグメント)"
if defined CANCEL goto gl_src
:gl_xliff
call :ask GXLIFF FILEOPT "確定 XLIFF (EN->JA セグメント)"
if defined CANCEL goto gl_html
if defined GSRC goto gl_out
if defined GHTML goto gl_out
if defined GXLIFF goto gl_out
echo  ※ 入力がありません。
choice /c RC /n /m "  再入力(R) / キャンセル(C): "
if errorlevel 2 goto menu
goto gl_src
:gl_out
call :ask GOUT TEXT "出力プレフィックス (<prefix>.csv/.json)"
if defined CANCEL goto gl_xliff
call :save
set "GARGS=--out "%GOUT%" --cache-dir "%CACHE%""
if defined GSRC   set "GARGS=!GARGS! --source "%GSRC%""
if defined GHTML  set "GARGS=!GARGS! --html "%GHTML%""
if defined GXLIFF set "GARGS=!GARGS! --xliff "%GXLIFF%""
if exist "%UNIV%" set "GARGS=!GARGS! --tmx "%UNIV%""
if defined PROD if exist "%PROD%" set "GARGS=!GARGS! --product-tmx "%PROD%""
if defined GXLIFF (
  choice /c YN /n /m "  XLIFF は確定行のみ使用しますか? (Y/N): "
  if not errorlevel 2 set "GARGS=!GARGS! --confirmed-only"
)
echo.
echo 実行中... (TM 補完を使う場合、索引が未キャッシュの初回のみ数分)
python "%GLOSSARY%" !GARGS!
echo.
echo 完了。"%GOUT%.csv" (Excel可) と "%GOUT%.json" を出力しました。
echo.
pause & goto menu

:newproj
echo.
echo === プロジェクト作成 ===
set "PNAME=" & set /p "PNAME=プロジェクト名: "
if not defined PNAME goto menu
set "PID="
for /f "usebackq delims=" %%I in (`python "%PROJECTS%" create --name "!PNAME!"`) do set "PID=%%I"
if not defined PID (echo  作成に失敗しました。& pause & goto menu)
rem 既定 TM を初期表示 (Enter で採用)。メイン=University / Product=Product / サブ=未設定
set "MAINTM=%UNIV%"
set "PRODTM=%PROD%"
set "SUBTM="

:np_src
cls
echo === プロジェクト作成: 「!PNAME!」  (1) ソースの追加 ===
echo  現在のソース:
python "%PROJECTS%" srcs --id "!PID!"
echo --------------------------------------------------
echo   F = ファイル追加     D = フォルダー追加(階層維持)
echo   U = 直前を取り消す   X = 次へ(メイン TM)
choice /c FDUX /n /m "  選択 (F/D/U/X): "
if errorlevel 4 goto np_tm
if errorlevel 3 goto np_undo_src
if errorlevel 2 goto np_dir
set "SRC1=" & call :ask SRC1 FILE "追加するソース .mdx"
if defined CANCEL goto np_src
python "%PROJECTS%" add-source --id "!PID!" --kind file --path "!SRC1!" >nul
goto np_src
:np_dir
set "DIR1=" & call :ask DIR1 DIR "追加するフォルダー (配下の .mdx を階層維持で対象)"
if defined CANCEL goto np_src
python "%PROJECTS%" add-source --id "!PID!" --kind dir --path "!DIR1!" >nul
goto np_src
:np_undo_src
python "%PROJECTS%" undo-source --id "!PID!"
pause & goto np_src

:np_tm
cls
echo === プロジェクト作成: 「!PNAME!」  (2) メイン TM（1つ・マッチ用）===
echo   A = 既存の TM を指定    N = 新規作成(空 TMX)
choice /c AN /n /m "  選択 (A/N): "
if errorlevel 2 goto np_tm_new
call :ask MAINTM FILE "メイン TM (.tmx)"
if defined CANCEL goto np_src
python "%PROJECTS%" set-main-tm --id "!PID!" --path "!MAINTM!" >nul
goto np_prod
:np_tm_new
set "NTM2=" & set /p "NTM2=新規メイン TM のフルパス (.tmx): "
if not defined NTM2 goto np_tm
python "%PROJECTS%" new-tm --path "!NTM2!"
python "%PROJECTS%" set-main-tm --id "!PID!" --path "!NTM2!" >nul
set "MAINTM=!NTM2!"
goto np_prod

:np_prod
cls
echo === プロジェクト作成: 「!PNAME!」  (3) Product TM（用語集ヒント・1つ・任意）===
echo  メイン TM: !MAINTM!
echo  Product TM は UI 用語の一致＋AI 翻訳の用語集ヒントに使います（旧 [1]/[2] の Product）。
echo   A = 既存の TM を指定   S = 使わない(スキップ)
choice /c AS /n /m "  選択 (A/S): "
if errorlevel 2 (
  set "PRODTM="
  python "%PROJECTS%" set-product-tm --id "!PID!" --path "" >nul
  goto np_sub
)
call :ask PRODTM FILE "Product TM (.tmx)"
if defined CANCEL goto np_tm
python "%PROJECTS%" set-product-tm --id "!PID!" --path "!PRODTM!" >nul
goto np_sub

:np_sub
cls
echo === プロジェクト作成: 「!PNAME!」  (4) サブ TM（複数可・マッチ用・任意）===
echo  メイン TM: !MAINTM!
echo  Product TM: !PRODTM!
echo  現在のサブ TM:
python "%PROJECTS%" subs --id "!PID!"
echo --------------------------------------------------
echo   A = サブ TM を追加   N = 新規作成(空 TMX)
echo   U = 直前を取り消す   X = 次へ(追加情報)
choice /c ANUX /n /m "  選択 (A/N/U/X): "
if errorlevel 4 goto np_meta
if errorlevel 3 goto np_undo_sub
if errorlevel 2 goto np_newtm
call :ask SUBTM FILE "追加するサブ TM (.tmx)"
if defined CANCEL goto np_sub
python "%PROJECTS%" add-sub-tm --id "!PID!" --path "!SUBTM!" >nul
goto np_sub
:np_newtm
set "NTM=" & set /p "NTM=新規サブ TM のフルパス (.tmx): "
if not defined NTM goto np_sub
python "%PROJECTS%" new-tm --path "!NTM!"
python "%PROJECTS%" add-sub-tm --id "!PID!" --path "!NTM!" >nul
goto np_sub
:np_undo_sub
python "%PROJECTS%" undo-sub-tm --id "!PID!"
pause & goto np_sub

:np_meta
cls
echo === プロジェクト作成: 「!PNAME!」  (4) 追加情報（任意・Enter でスキップ）===
set "OUTD=%OUTDIR%\Kotonoha-out\!PNAME!"
echo  出力先フォルダー 既定: !OUTD!
set "I_OUT=" & set /p "I_OUT=  変更する場合のみ入力: "
if defined I_OUT set "OUTD=!I_OUT!"
python "%PROJECTS%" set-outdir --id "!PID!" --path "!OUTD!" >nul
set "ASG=" & set /p "ASG=  担当者 (任意): "
if defined ASG python "%PROJECTS%" set-assignee --id "!PID!" --assignee "!ASG!" >nul
set "DUEV=" & set /p "DUEV=  期日 YYYY-MM-DD (任意): "
if defined DUEV python "%PROJECTS%" set-due --id "!PID!" --due "!DUEV!" >nul
set "MEMOV=" & set /p "MEMOV=  メモ (任意): "
if defined MEMOV python "%PROJECTS%" set-memo --id "!PID!" --memo "!MEMOV!" >nul

:np_done
cls
echo === 作成したプロジェクトの内容 ===
python "%PROJECTS%" show --id "!PID!"
echo --------------------------------------------------
echo プロジェクト定義を保存しました（[P] で一覧確認できます）。
echo.
choice /c YN /n /m "今すぐ 解析＋Pre-translation を実行しますか? (Y=実行 / N=メニューへ): "
if errorlevel 2 goto menu
goto run_proj

rem ===== プロジェクト定義で 解析+Pre-translation を実行 (!PID! を使用) =====
rem   戻り先は RUNRET (未設定なら menu)。combined.mt-todo を出力し成果物を台帳へ登録。
:run_proj
echo.
echo === 解析 + Pre-translation 実行 (プロジェクト定義) ===
echo 実行中... (索引が未キャッシュの初回のみ数分。以後は数秒)
python "%PROJECTS%" run --id "!PID!" --cache-dir "%CACHE%" --template "%TPL%" --engine "%SCRIPT%"
python "%PROJECTS%" dashboard --out "%~dp0_projects.html" >nul 2>nul
echo.
echo 完了。成果物を過去のプロジェクトに登録しました（メニュー [P] で再開可）。
echo 次: 出力フォルダーの combined.mt-todo.json の新規(^<=74%%)を Claude で翻訳し
echo     combined.mt-done.jsonl を作成 → メニュー [4] で一括注入。
echo.
pause
if defined RUNRET (set "RET=%RUNRET%" & set "RUNRET=" & goto !RET!)
goto menu

:projects
rem 一覧ダッシュボードを再生成してブラウザの別タブで開く
python "%PROJECTS%" dashboard --out "%~dp0_projects.html" >nul 2>nul
start "" "%~dp0_projects.html"
:projects_menu
cls
echo ==================================================
echo    過去のプロジェクト  (一覧はブラウザのタブに表示)
echo ==================================================
python "%PROJECTS%" list
echo --------------------------------------------------
echo  ブラウザ一覧の「開く」で TEP を別タブで再開できます。
echo  N = 新規作成([C])   G = 保存した定義を実行(解析+Pre-translation)
echo  X = 元形式で翻訳版を出力 (TM適用／TEP書き戻し後に実行)
echo  番号 = コンソールから開く   S=状態  M=メモ  E=期日  D=削除
echo  R = 一覧を再表示(再生成)   Enter = メニューへ
echo --------------------------------------------------
set "PA=" & set /p "PA=操作 (N / G / X / 番号 / S / M / E / D / R): "
if not defined PA goto menu
if /i "%PA%"=="N" goto newproj
if /i "%PA%"=="G" goto projects_run
if /i "%PA%"=="X" goto projects_export
if /i "%PA%"=="S" goto projects_status
if /i "%PA%"=="M" goto projects_memo
if /i "%PA%"=="E" goto projects_due
if /i "%PA%"=="D" goto projects_delete
if /i "%PA%"=="R" goto projects
set "PHTML="
for /f "usebackq delims=" %%H in (`python "%PROJECTS%" get --index %PA%`) do set "PHTML=%%H"
if not defined PHTML (
  rem 成果物 HTML が無い＝「保存した定義」の行。実行(G)を促す。
  set "RID="
  for /f "usebackq delims=" %%I in (`python "%PROJECTS%" idof --index %PA%`) do set "RID=%%I"
  if defined RID (
    echo  この行は「保存した定義」です（まだ解析していません）。
    choice /c RM /n /m "  R=今すぐ実行(解析+Pre-translation) / M=戻る: "
    if errorlevel 2 goto projects_menu
    set "PID=!RID!"
    set "RUNRET=projects_menu"
    goto run_proj
  )
  echo  その番号のプロジェクトが見つかりません。& pause & goto projects_menu
)
if not exist "!PHTML!" (echo  HTML が見つかりません: !PHTML! & pause & goto projects_menu)
start "" "!PHTML!"
echo  開きました。ブラウザで続きの TEP・確定を行えます。
pause & goto projects_menu

:projects_run
set "PN=" & set /p "PN=実行する定義の番号 (「ソースN件/サブTM...」の行): "
if not defined PN goto projects_menu
set "RID="
for /f "usebackq delims=" %%I in (`python "%PROJECTS%" idof --index %PN%`) do set "RID=%%I"
if not defined RID (
  echo  その番号は「保存した定義」ではありません（[C] で作成した行のみ実行可）。
  pause & goto projects_menu
)
set "PID=!RID!"
set "RUNRET=projects_menu"
goto run_proj

:projects_export
set "PN=" & set /p "PN=元形式で出力する定義の番号 (「ソースN件/サブTM...」の行): "
if not defined PN goto projects_menu
set "RID="
for /f "usebackq delims=" %%I in (`python "%PROJECTS%" idof --index %PN%`) do set "RID=%%I"
if not defined RID (
  echo  その番号は「保存した定義」ではありません（[C] で作成した行のみ出力可）。
  pause & goto projects_menu
)
echo.
echo === 元形式で翻訳版を出力 (プロジェクト TM を適用) ===
echo  ※ TEP 結果を TM に書き戻した後（[7]）に実行すると全文が訳出されます。
echo     未訳の文はそのまま原文で出力します。
choice /c YNC /n /m "  未訳文に〔未訳〕マークを付けますか? (Y=付ける / N=付けない / C=戻る): "
if errorlevel 3 goto projects_menu
if errorlevel 2 (set "XMARK=") else (set "XMARK=--mark-missing")
echo.
echo 実行中... (索引が未キャッシュの初回のみ数分。以後は数秒)
python "%PROJECTS%" export --id "!RID!" --cache-dir "%CACHE%" !XMARK!
echo.
echo 完了。出力フォルダーの translated\ に元形式の翻訳版を出力しました。
echo.
pause & goto projects_menu

:projects_status
set "PN=" & set /p "PN=状態を変える番号: "
if not defined PN goto projects_menu
choice /c 123 /n /m "  1=作業中 / 2=レビュー中 / 3=完了 : "
if errorlevel 3 (set "NS=完了") else if errorlevel 2 (set "NS=レビュー中") else (set "NS=作業中")
python "%PROJECTS%" set-status --index %PN% --status "!NS!"
python "%PROJECTS%" dashboard --out "%~dp0_projects.html" >nul 2>nul
echo  状態を「!NS!」に変更しました（ブラウザは F5 で更新）。
pause & goto projects_menu

:projects_memo
set "PN=" & set /p "PN=メモを編集する番号: "
if not defined PN goto projects_menu
set "MEMO=" & set /p "MEMO=メモ (空Enter=クリア): "
python "%PROJECTS%" set-memo --index %PN% --memo "!MEMO!"
python "%PROJECTS%" dashboard --out "%~dp0_projects.html" >nul 2>nul
echo  メモを更新しました（ブラウザは F5 で更新）。
pause & goto projects_menu

:projects_due
set "PN=" & set /p "PN=期日を設定する番号: "
if not defined PN goto projects_menu
set "DUE=" & set /p "DUE=期日 YYYY-MM-DD (空Enter=クリア): "
python "%PROJECTS%" set-due --index %PN% --due "!DUE!"
python "%PROJECTS%" dashboard --out "%~dp0_projects.html" >nul 2>nul
echo  期日を更新しました（ブラウザは F5 で更新）。
pause & goto projects_menu

:projects_delete
set "PN=" & set /p "PN=削除する番号: "
if not defined PN goto projects_menu
echo  一覧から削除します。HTML ファイル自体はどうしますか?
choice /c KD /n /m "  K=ファイルは残す / D=ファイルも削除 : "
if errorlevel 2 (
  python "%PROJECTS%" remove --index %PN% --delete-file
) else (
  python "%PROJECTS%" remove --index %PN%
)
python "%PROJECTS%" dashboard --out "%~dp0_projects.html" >nul 2>nul
echo  削除しました（ブラウザは F5 で更新）。
pause & goto projects_menu

:preview
start "" "%TPL%"
goto menu

rem ===== 汎用入力: 現在値表示→入力→検証→無効なら 再入力(R)/キャンセル(C) =====
rem   %1=変数名  %2=種別(FILE/DIR/FILEOPT/DIROPT/TEXT/TEXTOPT)  %3=ラベル
rem   戻り: 変数を更新。キャンセル時は CANCEL=1、成功時は CANCEL=(空)
rem   ※ キャンセル後に一つ前の入力へ戻すのは呼び出し側 (goto 前ステップ)。
:ask
setlocal enabledelayedexpansion
:ask_loop
call set "cur=%%%~1%%"
set "inp="
if defined cur (
  echo   現在: !cur!
  set /p "inp=  %~3 [Enter=据置/変更のみ]: "
) else (
  set /p "inp=  %~3: "
)
if defined inp (set "val=!inp!") else (set "val=!cur!")
if defined val set "val=!val:"=!"
set "kind=%~2"
set "isopt="
if not "!kind:OPT=!"=="!kind!" set "isopt=1"
if defined isopt if "!val!"=="-" set "val="
if defined isopt if not defined val (endlocal & set "%~1=" & set "CANCEL=" & goto :eof)
if not defined val (echo   ※ 入力が空です。& goto ask_choice)
set "base=!kind:OPT=!"
if "!base!"=="FILE" if not exist "!val!" (echo   ※ ファイルが見つかりません: !val!& goto ask_choice)
if "!base!"=="DIR"  if not exist "!val!\" (echo   ※ フォルダーが見つかりません: !val!& goto ask_choice)
endlocal & set "%~1=%val%" & set "CANCEL=" & goto :eof
:ask_choice
choice /c RC /n /m "  再入力(R) / キャンセル(C=一つ前に戻る): "
if errorlevel 2 (endlocal & set "CANCEL=1" & goto :eof)
goto ask_loop

rem ===== 現在のパス設定を _paths.cfg に保存 =====
:save
> "%CFG%" (
  echo # Kotonoha beta6 last-used paths - auto-saved. 1行 KEY=VALUE。
  echo UNIV=!UNIV!
  echo PROD=!PROD!
  echo CACHE=!CACHE!
  echo LIVETM=!LIVETM!
  echo MASTER=!MASTER!
  echo PROJTM=!PROJTM!
  echo SRC=!SRC!
  echo SDIR=!SDIR!
  echo OUT=!OUT!
  echo ODIR=!ODIR!
  echo XF=!XF!
  echo XD=!XD!
  echo GSRC=!GSRC!
  echo GHTML=!GHTML!
  echo GXLIFF=!GXLIFF!
  echo GOUT=!GOUT!
)
goto :eof
