#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File comparison: Current vs Target translated English source.

Compares files between the Current-version folder and a Target-translated-version
folder and writes an Excel report to the Results folder. The report covers the
UNION of both folders: files only in Target -> "Not in C", files only in Current
-> "New".

Usage:
  python file_compare_fullset.py "<target_translated_folder>" [--label Fullset|Project]

Positional:
  target_translated   Folder holding the previously-translated English source set
                      (e.g. ...\\domo-documentation-hub-0608\\s\\article).

Options:
  --current PATH    Current-version folder (default: s\\article in GitHub-Main).
  --results PATH    Output folder for the Excel report (default: File comparison\\Results).
  --label  TEXT     Optional filename suffix -> File_Comparison-YYYYMMDD-LABEL.xlsx
                    (use Fullset / Project to keep same-day runs from colliding).
"""
import os, sys, io, re, hashlib, difflib, datetime, argparse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
import translatable_util as tu

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

DEFAULT_CUR = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\_________GitHub-Main\domo-documentation-hub\s\article"
DEFAULT_RESULTS = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\File comparison\__Results"

ap = argparse.ArgumentParser(add_help=True)
ap.add_argument("target_translated", nargs="?",
                help="Target translated version folder (required).")
ap.add_argument("--current", default=DEFAULT_CUR, help="Current version folder.")
ap.add_argument("--results", default=DEFAULT_RESULTS, help="Output folder.")
ap.add_argument("--label", default="", help="Optional filename suffix (e.g. Fullset, Project).")
ap.add_argument("--translatable-only", action="store_true",
                help="Count only translatable-text (Title/body prose) changes as Y; "
                     "ignore markup/meta changes and summarise them in the Note column.")
args = ap.parse_args()

if not args.target_translated:
    ap.error("Target translated version folder path is required.\n"
             '  Example: python file_compare_fullset.py "C:\\...\\domo-documentation-hub-0608\\s\\article" --label Fullset')

CUR = args.current
OLD = args.target_translated
RESULTS = args.results
LABEL = args.label.strip()
TRANS_ONLY = args.translatable_only

for label, path in (("Current", CUR), ("Target translated", OLD)):
    if not os.path.isdir(path):
        ap.error("%s folder not found: %s" % (label, path))

print("Current          :", CUR, flush=True)
print("Target translated:", OLD, flush=True)

def list_files(d):
    return {f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))}

def read_text(path):
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as e:
        return "", "read-error:%s" % getattr(e, "errno", "?")
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "decode-error"

def norm_lines(text):
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    return [ln.rstrip() for ln in t.split("\n")]

def norm_content(text):
    lines = norm_lines(text)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

def ymd(path):
    try:
        ts = os.path.getmtime(path)
        return datetime.datetime.fromtimestamp(ts).strftime("%Y%m%d")
    except OSError:
        return ""

def get_title(text):
    """Extract Article title from frontmatter `title: "..."`."""
    m = re.search(r'(?s)^\ufeff?\s*---\s*\n(.*?)\n---', text)
    block = m.group(1) if m else text[:2000]
    for pat in (r'(?mi)^\s*title\s*:\s*"([^"]*)"',
                r"(?mi)^\s*title\s*:\s*'([^']*)'",
                r'(?mi)^\s*title\s*:\s*(.+?)\s*$'):
        mm = re.search(pat, block)
        if mm:
            return mm.group(1).strip().strip('"\'')
    return ""

TAG_RE = re.compile(r'</?[A-Za-z][^>\n]*>')

def frontmatter_title_line(text):
    m = re.search(r'(?s)^\ufeff?\s*---\s*\n(.*?)\n---', text)
    block = m.group(1) if m else text[:2000]
    tm = re.search(r'(?mi)^\s*title\s*:\s*(.+?)\s*$', block)
    return tm.group(1).strip().strip('"\'') if tm else None

def classify_change(old_t, new_t):
    """Return (categories:list, examples:list) for a real (non-whitespace) change."""
    cats = []
    ot, nt = frontmatter_title_line(old_t), frontmatter_title_line(new_t)
    if (ot or nt) and ot != nt:
        cats.append("Title")
    old_n, new_n = norm_lines(old_t), norm_lines(new_t)
    sm = difflib.SequenceMatcher(None, old_n, new_n)
    removed, added = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed += [old_n[i] for i in range(i1, i2) if old_n[i].strip()]
        if tag in ("replace", "insert"):
            added += [new_n[j] for j in range(j1, j2) if new_n[j].strip()]
    changed_text = "\n".join(removed + added)
    if TAG_RE.search(changed_text):
        cats.append("Tags")
    if re.search(r'\d', changed_text):
        cats.append("Numbers")
    if re.search(r'[#%&@*/\\()\[\]{}<>|~^=+\u2013\u2014\u2018\u2019\u201c\u201d]', changed_text):
        cats.append("Symbols")
    body_removed = [l for l in removed if l.strip() and not l.strip().lower().startswith("title:")]
    if body_removed or added:
        if "Text body" not in cats:
            cats.append("Text body")
    seen = set(); ordered = []
    for c in ["Title", "Text body", "Tags", "Numbers", "Symbols"]:
        if c in cats and c not in seen:
            ordered.append(c); seen.add(c)
    examples = []
    for l in removed[:3]:
        examples.append("- " + l.strip()[:120])
    for l in added[:3]:
        examples.append("+ " + l.strip()[:120])
    return ordered, examples

def whitespace_note(old_t, new_t):
    notes = []
    if ("\r\n" in old_t) != ("\r\n" in new_t) or old_t.count("\r\n") != new_t.count("\r\n"):
        notes.append("Hard line break")
    o_raw = old_t.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    n_raw = new_t.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if o_raw != n_raw:
        notes.append("Space")
    return ", ".join(dict.fromkeys(notes)) or "Hard line break"

# ---- Changed volume: 変更された語数（現行版比の%表記）。追加も削除も + でカウント ----
def word_tokens(text):
    """空白区切りの語トークン一覧。"""
    return re.findall(r"\S+", text or "")

def changed_word_count(old_t, new_t):
    """old→new の語レベル差分（追加＋削除の両方を + でカウント）。"""
    a = word_tokens(old_t); b = word_tokens(new_t)
    sm = difflib.SequenceMatcher(None, a, b); cnt = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            cnt += (i2 - i1)   # 削除語も + として数える
        if tag in ("replace", "insert"):
            cnt += (j2 - j1)   # 追加語
    return cnt

def fmt_changed(cnt, cur_total):
    """"+N Words（+P.P%）" 形式。P% = cnt / 現行版総語数。"""
    pct = (cnt / cur_total * 100.0) if cur_total else 0.0
    return "+%d Words（+%.1f%%）" % (cnt, pct)

cur_files = list_files(CUR)
old_files = list_files(OLD)
common = sorted(cur_files & old_files)
cur_only = cur_files - old_files
old_only = old_files - cur_files

def scan(names, base):
    info = {}
    for n in names:
        p = os.path.join(base, n)
        t, err = read_text(p)
        h = None if err else hashlib.md5(norm_content(t).encode("utf-8")).hexdigest()
        info[n] = {"title": ("" if err else get_title(t)), "hash": h, "date": ymd(p), "err": err}
    return info

cur_only_info = scan(cur_only, CUR)
old_only_info = scan(old_only, OLD)

# rename detection: content-identical pairs between old-only and cur-only
cur_by_hash = {}
for n, d in cur_only_info.items():
    if d["hash"]:
        cur_by_hash.setdefault(d["hash"], []).append(n)
old_by_hash = {}
for n, d in old_only_info.items():
    if d["hash"]:
        old_by_hash.setdefault(d["hash"], []).append(n)
renames = []  # (old_name, cur_name)
for h, cnames in cur_by_hash.items():
    if h in old_by_hash and len(cnames) == 1 and len(old_by_hash[h]) == 1:
        renames.append((old_by_hash[h][0], cnames[0]))
renamed_cur = {c for _, c in renames}
renamed_old = {o for o, _ in renames}

rows = []
stat = {"Y":0,"N":0,"?":0,"New":0,"Not in C":0,"rename":0}

# common files
for name in common:
    cp, op = os.path.join(CUR, name), os.path.join(OLD, name)
    old_t, oerr = read_text(op)
    new_t, nerr = read_text(cp)
    cdate, tdate = ymd(cp), ymd(op)
    title = get_title(new_t) if not nerr else (get_title(old_t) if not oerr else "")
    if TRANS_ONLY:
        if oerr or nerr:
            rows.append([name, title, "?", "判定不能：", "", tdate, cdate, (oerr or nerr)]); stat["?"]+=1; continue
        if old_t == new_t:
            rows.append([name, title, "N", "", "", tdate, cdate, "No change"]); stat["N"]+=1; continue
        ot, ol = tu.translatable(old_t)
        nt, nl = tu.translatable(new_t)
        ignored = tu.ignored_categories(old_t, new_t)
        note = "、".join(ignored) if ignored else ""
        title_changed = (ot != nt); body_changed = (ol != nl)
        if title_changed or body_changed:
            cats = []
            if title_changed: cats.append("Title")
            if body_changed: cats.append("Text body")
            summary = "、".join(cats)
            chg = fmt_changed(changed_word_count(old_t, new_t), len(word_tokens(new_t)))
            rows.append([name, title, "Y", summary, chg, tdate, cdate, note]); stat["Y"]+=1
        else:
            rows.append([name, title, "N", "", "", tdate, cdate, note or "formatting"]); stat["N"]+=1
        continue
    if oerr or nerr:
        rows.append([name, title, "?", "判定不能：", "", tdate, cdate, (oerr or nerr)])
        stat["?"] += 1; continue
    if norm_content(old_t) == norm_content(new_t):
        if old_t == new_t:
            rows.append([name, title, "N", "", "", tdate, cdate, "No change"]); stat["N"]+=1
        else:
            rows.append([name, title, "N", "", "", tdate, cdate, whitespace_note(old_t, new_t)]); stat["N"]+=1
    else:
        cats, _ = classify_change(old_t, new_t)
        summary = "、".join(cats) if cats else "Text body"
        chg = fmt_changed(changed_word_count(old_t, new_t), len(word_tokens(new_t)))
        rows.append([name, title, "Y", summary, chg, tdate, cdate, ""]); stat["Y"]+=1

# renamed pairs (content identical, name changed) -> Changed は空欄（本文差分なし）
for old_name, cur_name in sorted(renames):
    d = cur_only_info[cur_name]
    rows.append([cur_name, d["title"], "Y", f"File name（{old_name} → {cur_name}）", "",
                 old_only_info[old_name]["date"], d["date"], "File name"])
    stat["rename"] += 1; stat["Y"] += 1

# current-only (not matched as rename) -> New（対象テキスト全量。現行版比なので +100.0%）
for name in sorted(cur_only - renamed_cur):
    d = cur_only_info[name]
    t, err = read_text(os.path.join(CUR, name))
    chg = "" if err else fmt_changed(len(word_tokens(t)), len(word_tokens(t)))
    rows.append([name, d["title"], "New", "", chg, "", d["date"], ""])
    stat["New"] += 1

# target-only (not matched as rename) -> Not in C（Changed は記入不要＝空欄）
for name in sorted(old_only - renamed_old):
    d = old_only_info[name]
    rows.append([name, d["title"], "Not in C", "", "", d["date"], "", ""])
    stat["Not in C"] += 1

# sort: Y, ?, Not in C, New, N; alpha within
order = {"Y":0,"?":1,"Not in C":2,"New":3,"N":4}
rows.sort(key=lambda r: (order.get(r[2],5), r[0].lower()))

# 出力先フォルダーが存在しない場合は、どこに出力するかを対話で尋ねる
# （非対話実行時＝標準入力が端末でない場合は、従来どおり既定パスを作成）
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
# Target translated date (MMDD): most common file date in the target folder
_counts = {}
for _n in old_files:
    _dt = ymd(os.path.join(OLD, _n))
    if _dt:
        _counts[_dt] = _counts.get(_dt, 0) + 1
target_date = max(_counts, key=_counts.get) if _counts else today
target_mmdd = target_date[4:8]
prefix = "File_Comparison" + (("-" + LABEL) if LABEL else "")

def _unique_path(p):
    """同名ファイルがある場合は -01, -02, ... を付けて未使用のパスを返す（既存を上書きしない）。"""
    if not os.path.exists(p):
        return p
    b, e = os.path.splitext(p)
    i = 1
    while os.path.exists("%s-%02d%s" % (b, i, e)):
        i += 1
    return "%s-%02d%s" % (b, i, e)

out = _unique_path(os.path.join(RESULTS, f"{prefix}_{today}-{target_mmdd}.xlsx"))

wb = Workbook(); ws = wb.active; ws.title = "Comparison"
headers = ["File name", "Article title", "Update", "Summary", "Changed",
           "Target translated date", "Current date", "Note"]
hfill = PatternFill("solid", fgColor="1F4E78"); hfont = Font(color="FFFFFF", bold=True)
fills = {
    "Y": PatternFill("solid", fgColor="FCE4D6"),
    "?": PatternFill("solid", fgColor="FFF2CC"),
    "New": PatternFill("solid", fgColor="E2EFDA"),
    "Not in C": PatternFill("solid", fgColor="D9D9D9"),
}
UPDATE_COL = 3
CHANGED_COL = 5
widths = [40, 45, 10, 70, 18, 20, 14, 22]
_thin = Side(style="thin", color="BFBFBF")
grid_border = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

def write_sheet(ws, data_rows):
    ws.append(headers)
    for c in range(1, len(headers)+1):
        cell = ws.cell(1, c); cell.fill = hfill; cell.font = hfont
        cell.alignment = Alignment(vertical="center")
    for r in data_rows:
        ws.append(r)
        row_i = ws.max_row
        upd = r[UPDATE_COL-1]
        if upd in fills:
            ws.cell(row_i, UPDATE_COL).fill = fills[upd]
        ws.cell(row_i, UPDATE_COL).alignment = Alignment(horizontal="center")
        ws.cell(row_i, CHANGED_COL).alignment = Alignment(horizontal="center")
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for r in range(2, ws.max_row+1):
        ws.cell(r, 4).alignment = Alignment(wrap_text=True, vertical="top")
        ws.cell(r, 2).alignment = Alignment(wrap_text=True, vertical="top")
    # thin grid border across the whole used range
    ncols = len(headers)
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=1, max_col=ncols):
        for cell in row:
            cell.border = grid_border
    # sort/filter dropdowns on the header row
    ws.auto_filter.ref = "A1:%s%d" % (get_column_letter(ncols), ws.max_row)
    ws.freeze_panes = "A2"

write_sheet(ws, rows)
ws_y = wb.create_sheet("Changed (Y)")
write_sheet(ws_y, [r for r in rows if r[2] == "Y"])

# Data sheet (最終シート): 実行メタ情報 -- 現行版/前回翻訳版フォルダーパス・作業日時
ws_data = wb.create_sheet("Data")
run_dt = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
ws_data.append(["Item", "Note"])
ws_data.append(["Current version folder", CUR])
ws_data.append(["Target translated folder", OLD])
ws_data.append(["Work date/time", run_dt])
for c in (1, 2):
    hc = ws_data.cell(1, c); hc.fill = hfill; hc.font = hfont
    hc.alignment = Alignment(vertical="center")
for r in range(2, ws_data.max_row + 1):
    ws_data.cell(r, 1).font = Font(bold=True)
    ws_data.cell(r, 1).alignment = Alignment(vertical="top")
    ws_data.cell(r, 2).alignment = Alignment(vertical="top", wrap_text=True)
ws_data.column_dimensions["A"].width = 34
ws_data.column_dimensions["B"].width = 95
for row in ws_data.iter_rows(min_row=1, max_row=ws_data.max_row, min_col=1, max_col=2):
    for cell in row:
        cell.border = grid_border
ws_data.freeze_panes = "A2"

# 保存。出力先が Excel で開かれている等でロックされている場合は別名(タイムスタンプ付き)で保存し、結果を失わない。
try:
    wb.save(out)
except PermissionError:
    alt = out[:-5] + "_" + datetime.datetime.now().strftime("%H%M%S") + ".xlsx"
    print("WARNING: 保存先が使用中です(Excel等で開いている可能性):", out, flush=True)
    print("  -> 別名で保存します:", alt, flush=True)
    wb.save(alt)
    out = alt

print("Current files    :", len(cur_files))
print("Target files     :", len(old_files))
print("Common           :", len(common))
print("Renames          :", stat["rename"])
print("Y (changed)      :", stat["Y"])
print("N (no change)    :", stat["N"])
print("? (undetermined) :", stat["?"])
print("New (Cur only)   :", stat["New"])
print("Not in C (Tgt)   :", stat["Not in C"])
print("Saved:", out)
print("--- changed (Y) file list ---")
for r in rows:
    if r[2] == "Y":
        print(r[0])
print("--- undetermined (?) file list ---")
for r in rows:
    if r[2] == "?":
        print(r[0], "|", r[7])
