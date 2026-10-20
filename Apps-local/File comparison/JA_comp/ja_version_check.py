# -*- coding: utf-8 -*-
"""JA Version Check: 日本語版が英語版と同じバージョンかをチェックする。

英語版(EN)と日本語版(JA)の記事を比較し、英語版と同じバージョンの日本語版が
存在するか（EN が翻訳後に更新されていないか）を判定して Excel レポートを作る。

判定方針:
  * 対応付け  : 同名ファイル優先。ファイル名が異なる場合は画像パス/リンクの一致率でMatch rate算出。
  * EN Updated: git 最終コミット日時(EN>JA) と 内容構造(画像/リンク/見出し) の併用。
  * 内容比較  : 要注意ペアを content-todo.json に書き出し、Claude が内容比較(Pass2)、
                --inject で done.jsonl を Excel に反映(Pass3)。

Update 区分: Identical / EN Updated / Not localized / Only Japanese / Not in C
"""
import argparse, os, sys, io, re, subprocess, datetime, json
from collections import Counter
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HUB = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\_________GitHub-Main\domo-documentation-hub"
DEFAULT_EN = os.path.join(HUB, "s", "article")
DEFAULT_JA = os.path.join(HUB, "ja", "s", "article")
DEFAULT_RESULTS = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\File comparison\__Results\JA version"
# TM(JA→EN 原文参照)。Kotonoha の索引キャッシュ場所を流用。
DEFAULT_TMX = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\XTM\20260902\Domo_Domo University-en_US-ja_JP-2026-09-02.tmx"
DEFAULT_TM_CACHE = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working\Kotonoha\Index"

ap = argparse.ArgumentParser()
ap.add_argument("--en", default=DEFAULT_EN, help="英語版フォルダー")
ap.add_argument("--ja", default=DEFAULT_JA, help="日本語版フォルダー(Current)")
ap.add_argument("--published", default="", help="Published Japanese version フォルダー(任意)")
ap.add_argument("--hub", default=HUB, help="git リポジトリ(コミット日時取得用)")
ap.add_argument("--results", default=DEFAULT_RESULTS, help="出力フォルダー")
ap.add_argument("--identical-min", "--pass2-threshold", dest="identical_min", type=float, default=99.0,
                help="Match rate(TMカバレッジ%%) がこの値以上を Identical、未満を EN Updated(要再翻訳)とする(既定99)")
ap.add_argument("--cover-sim", dest="cover_sim", type=float, default=0.6,
                help="Match rate算出時、EN文のTM訳とJA文の『カバー済』判定に使うトライグラム類似度しきい値(既定0.6)")
ap.add_argument("--tmx", default=DEFAULT_TMX, help="TM(JA→EN原文参照)の TMX")
ap.add_argument("--tm-cache", dest="tm_cache", default=DEFAULT_TM_CACHE, help="TM索引キャッシュ場所")
ap.add_argument("--no-tm", dest="no_tm", action="store_true", help="TM参照を使わない")
ap.add_argument("--inject", default="", help="Pass3: content-done.jsonl を既存Excelに反映")
ap.add_argument("--xlsx", default="", help="--inject 時の対象Excel")
args = ap.parse_args()

# ---------------- 共通ヘルパー ----------------
def read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError:
        return "", "read-error"
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "decode-error"

def split_fm(text):
    m = re.search(r"(?s)^\ufeff?\s*---\s*\n(.*?)\n---\s*\n?", text)
    if m:
        return m.group(1), text[m.end():]
    return "", text

def get_title(text):
    fm, _ = split_fm(text)
    block = fm or text[:2000]
    for pat in (r'(?mi)^\s*title\s*:\s*"([^"]*)"',
                r"(?mi)^\s*title\s*:\s*'([^']*)'",
                r'(?mi)^\s*title\s*:\s*(.+?)\s*$'):
        mm = re.search(pat, block)
        if mm:
            return mm.group(1).strip().strip('"\'')
    return ""

CODE = re.compile(r'(?s)```.*?```')
INLINE_CODE = re.compile(r'`[^`]*`')

# 本ツールは URL・画像・日付・見出し数を比較に使わず、テキスト本文のみを TM 経由で比較する。
def text_segments(body):
    """本文を TM 照合用の文/行に分割する。frontmatter とコード例(フェンス/インライン)を除き、
    箇条書き/見出し/引用/表の markdown 記号を落とし、短すぎる行を除外。"""
    b = split_fm(body)[1]
    b = INLINE_CODE.sub(" ", CODE.sub(" ", b))
    segs = []
    for ln in b.split("\n"):
        ln = re.sub(r"^\s*[-*+#>|]+\s*", "", ln).strip()   # 行頭の markdown 記号を除去
        ln = re.sub(r"\s{2,}", " ", ln)
        if len(ln) >= 12 and not ln.startswith("import"):
            segs.append(ln)
    return segs

def list_mdx(d):
    if not d or not os.path.isdir(d):
        return {}
    return {f: os.path.join(d, f) for f in os.listdir(d)
            if f.lower().endswith(".mdx") and os.path.isfile(os.path.join(d, f))}

def _git_exe():
    """git.exe を解決（PATH→よくあるインストール先）。"""
    import shutil
    g = shutil.which("git")
    if g:
        return g
    for p in (os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Programs\Git\cmd\git.exe"),
              r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if p and os.path.exists(p):
            return p
    return "git"

def git_last_dates(hub, *relroots):
    """1回の git log で、各ファイル(repo相対パス)の最終コミット日(YYYY-MM-DD)を取得。"""
    dates = {}
    try:
        cp = subprocess.run(
            [_git_exe(), "-C", hub, "log", "--no-renames", "--pretty=format:\x01%cs", "--name-only",
             "--", *relroots],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        cur = None
        for line in cp.stdout.split("\n"):
            if line.startswith("\x01"):
                cur = line[1:].strip()
            elif line.strip() and cur:
                p = line.strip()
                if p not in dates:
                    dates[p] = cur
    except Exception as e:
        print("  (git 日時取得に失敗: %s / 日付は空欄になります)" % e, flush=True)
    return dates

def relkey(hub, path):
    try:
        return os.path.relpath(path, hub).replace("\\", "/")
    except ValueError:
        return ""

# =================== Pass3: inject ===================
if args.inject:
    xlsx = args.xlsx
    if not xlsx or not os.path.exists(xlsx):
        print("ERROR: --inject には有効な --xlsx が必要です", flush=True); sys.exit(1)
    done = {}
    txt = open(args.inject, encoding="utf-8-sig").read().strip()
    for ln in txt.split("\n"):
        ln = ln.strip()
        if not ln:
            continue
        rec = json.loads(ln)
        key = rec.get("en") or rec.get("ja") or rec.get("key")
        if key:
            done[key] = rec
    # Update 値の書き換えに合わせてセル色も再適用（降格/昇格で色が残らないように）
    _inj_fills = {
        "EN Updated":    PatternFill("solid", fgColor="FCE4D6"),
        "Mismatch":      PatternFill("solid", fgColor="FFC7CE"),
        "Not localized": PatternFill("solid", fgColor="FFF2CC"),
        "Only Japanese": PatternFill("solid", fgColor="DDEBF7"),
        "Not in C":      PatternFill("solid", fgColor="D9D9D9"),
        "Identical":     PatternFill("solid", fgColor="E2EFDA"),
    }
    wb = load_workbook(xlsx)
    ws = wb["Compare"]
    hdr = [c.value for c in ws[1]]
    col = {h: i + 1 for i, h in enumerate(hdr)}
    filled = 0
    for r in range(2, ws.max_row + 1):
        en = ws.cell(r, col.get("EN File name", 1)).value or ""
        ja = ws.cell(r, col.get("JA File name", 2)).value or ""
        rec = done.get(en) or done.get(ja)
        if not rec:
            continue
        if rec.get("update"):
            uc = ws.cell(r, col["Update"])
            uc.value = rec["update"]
            if rec["update"] in _inj_fills:               # 新しい判定に合わせて色を貼り直す
                uc.fill = _inj_fills[rec["update"]]
        if rec.get("summary") is not None:
            ws.cell(r, col["Summary"]).value = rec["summary"]
        if rec.get("match_rate") is not None and "Match rate" in col:
            ws.cell(r, col["Match rate"]).value = rec["match_rate"]
        if rec.get("note") is not None:
            ws.cell(r, col["Note"]).value = rec["note"]
        filled += 1
    wb.save(xlsx)
    print("injected:", filled, "rows ->", xlsx, flush=True)
    sys.exit(0)

# =================== Pass1: check ===================
EN, JA, PUB = args.en, args.ja, args.published
for label, p in (("EN", EN), ("JA", JA)):
    if not os.path.isdir(p):
        print("ERROR: %s フォルダーが見つかりません: %s" % (label, p), flush=True); sys.exit(1)

print("EN       :", EN, flush=True)
print("JA       :", JA, flush=True)
if PUB:
    print("Published:", PUB, flush=True)

en_files = list_mdx(EN)
ja_files = list_mdx(JA)
pub_files = list_mdx(PUB) if PUB else {}
print("EN: %d files | JA: %d files%s" % (len(en_files), len(ja_files),
      (" | Published JA: %d" % len(pub_files)) if PUB else ""), flush=True)

# ---- git 日時 ----
print("git 最終コミット日時を取得中...", flush=True)
gdates = git_last_dates(args.hub, relkey(args.hub, EN), relkey(args.hub, JA))
def gdate(path):
    return gdates.get(relkey(args.hub, path), "")

# ---- 各ファイルの情報を先読み ----
def load_info(path):
    t, err = read_text(path)
    return {"title": ("" if err else get_title(t)), "body": t, "err": err}

en_info = {n: load_info(p) for n, p in en_files.items()}
ja_info = {n: load_info(p) for n, p in ja_files.items()}

# ---- TM 索引(EN→JA / JA→EN)を準備 ----
tmidx = None
if not args.no_tm and args.tmx and os.path.exists(args.tmx):
    try:
        import tm_ja_en
        print("TM索引(EN<->JA)を準備中... (初回のみ数十秒)", flush=True)
        tmidx = tm_ja_en.load_or_build([args.tmx], args.tm_cache, log=lambda *a: print(*a, flush=True))
    except Exception as e:
        print("  (TM索引の準備に失敗: %s / TM機能は無効)" % e, flush=True)
        tmidx = None

def _ja_sentence_index(ja_body):
    """JA本文を文集合(norm_ja)に分解し、各文のトライグラム集合とトライグラム転置索引を返す。
    あいまい一致(カバレッジ)を候補文だけで高速に計算するための前処理。"""
    sents = []          # [(norm_sentence, trigram_set)]
    inv = {}            # trigram -> [sentence idx]
    seen = set()
    for seg in text_segments(ja_body):
        ns = tm_ja_en.norm_ja(seg)
        if not ns or ns in seen:
            continue
        seen.add(ns)
        tg = tm_ja_en.trigrams(ns)
        i = len(sents); sents.append((ns, tg))
        for t in tg:
            inv.setdefault(t, []).append(i)
    return sents, inv

def tm_coverage(en_body, ja_body):
    """EN本文を文単位でTM(EN→JA)参照し、その訳文がJA本文でカバーされる割合(%)を返す。
    = EN内容のJAカバレッジ率(Match rate)。カバー判定は「完全一致(部分文字列)」または
    「JAいずれかの文とトライグラム類似度>=cover-sim」。後編集で字面が変わった訳も拾える。
    TMに訳が無いEN文は分母から除外。判定不能は (None,0,0)。"""
    if not tmidx:
        return None, 0, 0
    ja_norm = tm_ja_en.norm_ja(ja_body)                 # 完全一致(高速)チェック用
    sents, inv = _ja_sentence_index(ja_body)            # あいまい一致用
    sim = args.cover_sim
    total = covered = 0
    for seg in text_segments(en_body):
        ja_ref = tm_ja_en.lookup_en2ja_exact(tmidx, seg)   # EN文→TM訳(JA, exact)
        if not ja_ref:
            continue
        total += 1
        if ja_ref in ja_norm:                            # 完全一致
            covered += 1
            continue
        q = tm_ja_en.trigrams(ja_ref)                    # あいまい一致: 候補文のみ比較
        if not q:
            continue
        cand = set()
        for t in q:
            cand.update(inv.get(t, ()))
        for i in cand:
            tg = sents[i][1]
            if (len(q & tg) / len(q | tg) if (q | tg) else 0.0) >= sim:
                covered += 1
                break
    if total == 0:
        return None, 0, 0
    return round(covered / total * 100.0, 1), covered, total

def _tm_title_ja(en_title):
    """EN title の TM 訳(norm_ja)。exact 優先、無ければあいまい照合(件数が少ないので可)。"""
    if not tmidx or not en_title:
        return None
    ja_ref = tm_ja_en.lookup_en2ja_exact(tmidx, en_title)
    if ja_ref:
        return ja_ref
    ja_ref, _ = tm_ja_en.lookup_en2ja(tmidx, en_title)
    return ja_ref

def title_matches(ja_ref, ja_title):
    """TM訳した EN title(ja_ref) と JA title が一致(正規化一致/包含/高類似)するか。"""
    jt = tm_ja_en.norm_ja(ja_title)
    if not ja_ref or not jt:
        return False
    if ja_ref == jt or ja_ref in jt or jt in ja_ref:
        return True
    a, b = tm_ja_en.trigrams(ja_ref), tm_ja_en.trigrams(jt)
    return bool(a and b) and (len(a & b) / len(a | b) >= 0.6)

# ---- 対応付け: ①ファイル名一致 ②Title一致(TM訳) ③内容(TM)。日付/画像/URLは不使用 ----
en_names = set(en_files); ja_names = set(ja_files)
pairs = []                       # (en_name, ja_name, method)
matched_en = set(); matched_ja = set()
tm_notes = {}

# ① ファイル名(コード)一致
for n in sorted(en_names & ja_names):
    pairs.append((n, n, "filename")); matched_en.add(n); matched_ja.add(n)

# ② Title 一致(EN title を TM で訳し JA title と比較)。訳は EN ごとに一度だけ計算(高速化)
if tmidx:
    en_title_ja = {en: _tm_title_ja(en_info[en]["title"]) for en in sorted(en_names - matched_en)}
    for jn in sorted(ja_names - matched_ja):
        jt = ja_info[jn]["title"]
        if not jt:
            continue
        for en in sorted(en_names - matched_en):
            if en in matched_en:
                continue
            if title_matches(en_title_ja.get(en), jt):
                pairs.append((en, jn, "title")); matched_en.add(en); matched_ja.add(jn)
                tm_notes[jn] = "Title一致(TM訳)"
                break

# ③ 内容(TM): 残りの JA を、日本語本文→TM(JA→EN)原文→EN本文照合で対応付け
if tmidx:
    avail_en = sorted(en_names - matched_en)
    en_norm = {e: tm_ja_en.norm_en(en_info[e]["body"]) for e in avail_en}
    for jn in sorted(ja_names - matched_ja):
        found_en, snippet = None, None
        for js in sorted(text_segments(ja_info[jn]["body"]), key=len, reverse=True)[:5]:
            ens, _ = tm_ja_en.lookup(tmidx, js)
            if ens and len(ens) >= 12:
                if snippet is None:
                    snippet = ens
                key = tm_ja_en.norm_en(ens)
                for e in avail_en:
                    if e not in matched_en and key and key in en_norm[e]:
                        found_en = e; break
                if found_en:
                    break
        if found_en:
            pairs.append((found_en, jn, "content")); matched_en.add(found_en); matched_ja.add(jn)
            tm_notes[jn] = "内容照合(TM原文): " + (snippet[:80] if snippet else "")
        # 英語版が見つからない(=Only Japanese)場合は TM原文候補 を付けない。
        # 理由: オリジナルの英語版ソースは既にリポジトリから削除済みのため、TM候補を示す意味がない。

# ---- Update 判定 ----
# Mismatch(別記事の可能性)は「同コード名なのに EN title の TM訳が JA title と対応しない」で判定。
#   ※極低Match rateでの判定はTM未収載の同一記事(短い記事等)を誤検出するため用いない。
# それ以外は Match rate(TMカバレッジ)で: >=identical-min(既定99)=Identical、未満/判定不能=EN Updated(要再翻訳)。
# Match rate は「EN各文のTM訳がJA本文でカバーされる割合(あいまい一致)」。Pass2は行わない。
TH = args.identical_min
def classify(mr):
    if mr is None:
        return "EN Updated", "TM収載のEN文が無くカバレッジ算出不可。要確認/再翻訳"
    if mr >= TH:
        return "Identical", ("" if mr >= 100.0 else "TMカバレッジ %.1f%%(しきい値%.0f%%以上)" % (mr, TH))
    return "EN Updated", "TMカバレッジ %.1f%%（JAに未対応のEN文あり・要再翻訳）" % mr

# ---- 行の組み立て ----
rows = []
stat = Counter()
for en_name, ja_name, method in pairs:
    ei = en_info[en_name]; ji = ja_info[ja_name]
    mr, cov, tot = tm_coverage(ei["body"], ji["body"])
    ed = gdate(en_files[en_name]); jd = gdate(ja_files[ja_name])
    mr_cell = "" if mr is None else mr
    update, summary = classify(mr)
    rows.append([en_name, ja_name, ei["title"], ji["title"], update, summary, mr_cell, jd, ed, tm_notes.get(ja_name, "")])
    stat[update] += 1

# Not localized: EN のみ(対応 JA なし)
for en_name in sorted(en_names - matched_en):
    ei = en_info[en_name]
    rows.append([en_name, "", ei["title"], "", "Not localized", "日本語版なし", "", "", gdate(en_files[en_name]), ""])
    stat["Not localized"] += 1

# Only Japanese: JA のみ(対応 EN なし)
for ja_name in sorted(ja_names - matched_ja):
    ji = ja_info[ja_name]
    rows.append(["", ja_name, "", ji["title"], "Only Japanese", "英語版なし", "", gdate(ja_files[ja_name]), "", tm_notes.get(ja_name, "")])
    stat["Only Japanese"] += 1

# Published JA vs Current EN: Current(EN/JA)に無い Published JA を Not in C
if PUB:
    cur_all = en_names | ja_names
    for pn in sorted(set(pub_files) - cur_all):
        pi = load_info(pub_files[pn])
        rows.append(["", pn, "", pi["title"], "Not in C", "Current版に存在しない(Published JA のみ)",
                     "", gdate(pub_files[pn]), "", ""])
        stat["Not in C"] += 1

# ---- 並び順: EN Updated → Not localized → Only Japanese → Not in C → Identical ----
order = {"EN Updated": 0, "Mismatch": 1, "Not localized": 2, "Only Japanese": 3, "Not in C": 4, "Identical": 5}
rows.sort(key=lambda r: (order.get(r[4], 5), (r[0] or r[1]).lower()))

# ---- 出力先 ----
RESULTS = args.results
if not os.path.isdir(RESULTS):
    _ans = ""
    if sys.stdin and sys.stdin.isatty():
        try:
            print("出力先フォルダーが存在しません:", RESULTS, flush=True)
            _ans = input("出力先フォルダーのフルパスを入力してください（Enter で上記を作成）: ").strip().strip('"')
        except (EOFError, KeyboardInterrupt):
            _ans = ""
    if _ans:
        RESULTS = _ans
    os.makedirs(RESULTS, exist_ok=True)

today = datetime.datetime.now().strftime("%Y%m%d")
def _latest_base(results, today):
    """最新版は常に番号なし(JA_version-YYYYMMDD.xlsx)。既存の最新版があれば -NN(既存最大+1)へ
    退避してから最新版用に空ける(旧版は削除しない=古い順に -01,-02 …)。"""
    numre = re.compile(r"^JA_version-" + re.escape(today) + r"-(\d+)\.xlsx$")
    base = os.path.join(results, "JA_version-%s.xlsx" % today)
    if os.path.exists(base):
        mx = 0
        for f in os.listdir(results):
            m = numre.match(f)
            if m:
                mx = max(mx, int(m.group(1)))
        arch = os.path.join(results, "JA_version-%s-%02d.xlsx" % (today, mx + 1))
        try:
            os.replace(base, arch)
            print("  旧版を退避:", os.path.basename(arch), flush=True)
        except OSError as e:
            print("  (旧版を退避できません: %s / 新規を番号付きで保存)" % e, flush=True)
            i = mx + 1
            while os.path.exists(os.path.join(results, "JA_version-%s-%02d.xlsx" % (today, i))):
                i += 1
            return os.path.join(results, "JA_version-%s-%02d.xlsx" % (today, i))
    return base
out = _latest_base(RESULTS, today)

# ---- Excel ----
wb = Workbook(); ws = wb.active; ws.title = "Compare"
headers = ["EN File name", "JA File name", "EN Article title", "JA Article title",
           "Update", "Summary", "Match rate", "Target translated date", "Current date", "Note"]
hfill = PatternFill("solid", fgColor="1F4E78"); hfont = Font(color="FFFFFF", bold=True)
fills = {
    "EN Updated":    PatternFill("solid", fgColor="FCE4D6"),
    "Mismatch":      PatternFill("solid", fgColor="FFC7CE"),
    "Not localized": PatternFill("solid", fgColor="FFF2CC"),
    "Only Japanese": PatternFill("solid", fgColor="DDEBF7"),
    "Not in C":      PatternFill("solid", fgColor="D9D9D9"),
    "Identical":     PatternFill("solid", fgColor="E2EFDA"),
}
UPDATE_COL = 5
widths = [26, 26, 40, 40, 14, 60, 11, 18, 14, 30]
_thin = Side(style="thin", color="BFBFBF")
grid = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

def write_sheet(ws, data_rows):
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(1, c); cell.fill = hfill; cell.font = hfont
        cell.alignment = Alignment(vertical="center")
    for r in data_rows:
        ws.append(r)
        i = ws.max_row
        upd = r[UPDATE_COL - 1]
        if upd in fills:
            ws.cell(i, UPDATE_COL).fill = fills[upd]
        ws.cell(i, UPDATE_COL).alignment = Alignment(horizontal="center")
        ws.cell(i, 7).alignment = Alignment(horizontal="center")   # Match rate
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for r in range(2, ws.max_row + 1):
        ws.cell(r, 3).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 4).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 6).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 10).alignment = Alignment(wrap_text=True, vertical="top")
    ncols = len(headers)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ncols):
        for cell in row:
            cell.border = grid
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(ncols), ws.max_row)
    ws.freeze_panes = "A2"

write_sheet(ws, rows)

# Data シート
ws_d = wb.create_sheet("Data")
run_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
ws_d.append(["Item", "Note"])
ws_d.append(["English version folder", EN])
ws_d.append(["Current Japanese version folder", JA])
ws_d.append(["Published Japanese version folder", PUB or "(not specified)"])
ws_d.append(["Work date/time", run_dt])
# Update 区分ごとの件数と合計
ws_d.append(["Update counts", ""])
_upd_order = ["Identical", "EN Updated", "Not localized", "Only Japanese", "Not in C"]
_upd_total = 0
for _k in _upd_order:
    _v = int(stat.get(_k, 0)); _upd_total += _v
    ws_d.append([_k, _v])
ws_d.append(["Total", _upd_total])
for c in (1, 2):
    hc = ws_d.cell(1, c); hc.fill = hfill; hc.font = hfont; hc.alignment = Alignment(vertical="center")
for r in range(2, ws_d.max_row + 1):
    ws_d.cell(r, 1).font = Font(bold=True)
    ws_d.cell(r, 1).alignment = Alignment(vertical="top")
    ws_d.cell(r, 2).alignment = Alignment(vertical="top", wrap_text=True)
ws_d.column_dimensions["A"].width = 34
ws_d.column_dimensions["B"].width = 95
for row in ws_d.iter_rows(min_row=1, max_row=ws_d.max_row, min_col=1, max_col=2):
    for cell in row:
        cell.border = grid
ws_d.freeze_panes = "A2"

try:
    wb.save(out)
except PermissionError:
    out = out[:-5] + "_" + datetime.datetime.now().strftime("%H%M%S") + ".xlsx"
    wb.save(out)

# ---- サマリー ----
print("\n== 結果 ==", flush=True)
for k in ["Identical", "EN Updated", "Not localized", "Only Japanese", "Not in C"]:
    print("  %-14s: %d" % (k, stat.get(k, 0)), flush=True)
print("Saved:", out, flush=True)
print("EN Updated = 要再翻訳（Match rate が identical-min 未満）", flush=True)
