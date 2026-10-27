# -*- coding: utf-8 -*-
"""Project registry + dashboard for the Kotonoha beta5 launcher.

Records each analyzed / Pre-translated article (過去のプロジェクトリスト) so work
can be resumed anytime: re-opening a project's work file (HTML) restores the TEP
edits/confirms the browser saved in localStorage. The project list is shown in its own
browser tab via a generated dashboard (_projects.html), separate from the work files.

Store: _projects.json next to this script (override with --store). Fields per project:
  html, title, source, segs, mt, status(作業中/レビュー中/完了), memo, due, created, updated

Commands:
  add        --html <path>           register one ([1]); title/source/MT from <html>.mt-todo.json
  add-batch  --combined <todo.json>  register every article in a combined mt-todo.json ([2])
  list       [--status S|--active]   numbered list (newest first); --active hides 完了
  get        --index N               print the N-th project's HTML path
  set-status --index N --status S    作業中 / レビュー中 / 完了
  set-memo   --index N --memo "..."  set/clear memo
  set-due    --index N --due "..."   set/clear due date
  remove     --index N [--delete-file]  drop from list (optionally delete the HTML + mt-todo)
  dashboard  [--out _projects.html]  (re)generate the browser dashboard
Indices match the numbers shown by `list` / the dashboard.
"""
import argparse, sys, io, os, json, datetime, html as _html
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_STORE = os.path.join(HERE, "_projects.json")
VERSION = "beta5.01"   # 画面バナー / EMPTY_TMX の creationtoolversion などに使用
STATUSES = ["作業中", "レビュー中", "完了"]

def load(store):
    if os.path.exists(store):
        try:
            return json.load(open(store, encoding="utf-8-sig")).get("projects", [])
        except Exception:
            return []
    return []

def save(store, projects):
    json.dump({"projects": projects}, open(store, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

def ncase(p):
    return os.path.normcase(os.path.abspath(p)) if p else ""

def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


# ===== 操作履歴（アクティビティログ）: _history.json（_projects.json の隣）=====
_HIST_CAP = 3000   # 肥大化防止（古いものから切り捨て）

def history_path(store):
    return os.path.join(os.path.dirname(os.path.abspath(store)), "_history.json")

def load_history(store):
    p = history_path(store)
    if os.path.exists(p):
        try:
            return json.load(open(p, encoding="utf-8-sig")).get("rows", [])
        except Exception:
            return []
    return []

def save_history(store, rows):
    json.dump({"rows": rows[-_HIST_CAP:]}, open(history_path(store), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

def log_history(store, action, detail="", project=""):
    """操作を1件追記。失敗してもメイン処理は止めない。"""
    try:
        rows = load_history(store)
        hid = "h-" + datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
        rows.append({"id": hid, "at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     "action": action, "detail": detail or "", "project": project or "", "memo": ""})
        save_history(store, rows)
    except Exception:
        pass

def history_update(store, hid, data):
    rows = load_history(store)
    for r in rows:
        if r.get("id") == hid:
            for k in ("detail", "memo"):
                if k in data:
                    r[k] = (data.get(k) or "")
            r["updated"] = now()
            break
    save_history(store, rows)
    return True

def history_delete(store, hid):
    rows = load_history(store)
    n = len(rows)
    rows[:] = [r for r in rows if r.get("id") != hid]
    save_history(store, rows)
    return n - len(rows)

# ===== 用語管理（termbase）: 全プロジェクト共通の単一 TSV =====
TERM_COLS = ["id", "source", "target", "example", "note", "doc", "project", "created", "updated"]
TERM_EXPORT = [("source", "ソース"), ("target", "ターゲット"), ("example", "用例"),
               ("note", "ノート"), ("doc", "ドキュメント"), ("project", "プロジェクト"), ("updated", "更新日")]

def default_term_store():
    """全体共通の用語集 TSV の既定パス（Live_TM 配下・なければスクリプト隣）。"""
    live = read_cfg().get("LIVETM", "")
    base = live if (live and os.path.isdir(live)) else HERE
    return os.path.join(base, "_terms.tsv")

def load_terms(path):
    if not path or not os.path.exists(path):
        return []
    import csv
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return [{c: (r.get(c) or "") for c in TERM_COLS}
                    for r in csv.DictReader(f, delimiter="\t")]
    except Exception:
        return []

def save_terms(path, rows):
    import csv
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TERM_COLS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: (r.get(c) or "") for c in TERM_COLS})

def make_term_id(rows):
    base = "term-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    ids = {r.get("id") for r in rows}
    tid = base; k = 1
    while tid in ids:
        k += 1; tid = base + "-" + str(k)
    return tid

def term_save(rows, data):
    """Add (no id) or update (id given) one term record. Returns the record."""
    tid = (data.get("id") or "").strip()
    rec = None
    if tid:
        for r in rows:
            if r.get("id") == tid:
                rec = r; break
    if rec is None:
        rec = {"id": make_term_id(rows), "created": now()}
        rows.append(rec)
    for k in ("source", "target", "example", "note", "doc", "project"):
        if k in data:
            rec[k] = (data.get(k) or "")
    rec["updated"] = now()
    return rec

def term_delete(rows, tid):
    before = len(rows)
    rows[:] = [r for r in rows if r.get("id") != tid]
    return before - len(rows)

def terms_for_segment(rows, seg):
    """Terms whose source appears in the segment text (case-insensitive substring)."""
    s = (seg or "").lower()
    if not s:
        return []
    out = [r for r in rows if (r.get("source") or "").strip()
           and (r.get("source") or "").strip().lower() in s]
    out.sort(key=lambda r: -len(r.get("source", "")))
    return out

def _write_xlsx(path, header, data_rows):
    """依存なしの最小 XLSX ライタ（inlineStr・日本語対応）。"""
    import zipfile
    def col(n):
        s = ""; n += 1
        while n:
            n, r = divmod(n - 1, 26); s = chr(65 + r) + s
        return s
    def esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    rows_xml = []
    for ri, row in enumerate([header] + data_rows, 1):
        cells = "".join('<c r="%s%d" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>'
                        % (col(ci), ri, esc(v)) for ci, v in enumerate(row))
        rows_xml.append('<row r="%d">%s</row>' % (ri, cells))
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>%s</sheetData></worksheet>' % "".join(rows_xml))
    wb = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
          'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
          '<sheets><sheet name="Terms" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wbrels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
              'Target="worksheets/sheet1.xml"/></Relationships>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
          '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
          '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)

def export_terms(rows, out_path, fmt="tsv"):
    fmt = (fmt or "tsv").lower()
    cols = [c for c, _ in TERM_EXPORT]; heads = [h for _, h in TERM_EXPORT]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    if fmt in ("tsv", "csv"):
        import csv
        with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=("\t" if fmt == "tsv" else ","))
            w.writerow(heads)
            for r in rows:
                w.writerow([(r.get(c) or "") for c in cols])
    elif fmt == "xlsx":
        _write_xlsx(out_path, heads, [[(r.get(c) or "") for c in cols] for r in rows])
    else:
        return {"ok": False, "error": "unknown format: %s" % fmt}
    return {"ok": True, "out": out_path, "count": len(rows)}

def upsert(projects, html, title=None, source=None, segs=None, mt=None, project=None,
           main_tm=None, product_tm=None, sub_tms=None, sources=None, out_dir=None, name=None):
    key = ncase(html)
    for p in projects:
        if ncase(p.get("html", "")) == key:
            if title is not None:  p["title"] = title
            if source is not None: p["source"] = source
            if segs is not None:   p["segs"] = segs
            if mt is not None:     p["mt"] = mt
            if project is not None: p["project"] = project
            # 各記事を“それ自身で実行/出力できる”独立プロジェクトにするためのレシピ
            if name is not None:        p["name"] = name
            if main_tm is not None:     p["main_tm"] = main_tm
            if product_tm is not None:  p["product_tm"] = product_tm
            if sub_tms is not None:     p["sub_tms"] = list(sub_tms)
            if sources is not None:     p["sources"] = sources
            if out_dir is not None:     p["out_dir"] = out_dir
            p["updated"] = now()
            return False
    projects.append({
        "id": make_id(projects),
        "html": html,
        "title": title or os.path.splitext(os.path.basename(html))[0],
        "name": name or title or "",
        "project": project or "",
        "source": source or "", "segs": segs, "mt": mt,
        "main_tm": main_tm or "", "product_tm": product_tm or "",
        "sub_tms": list(sub_tms) if sub_tms else [],
        "sources": sources or ([{"kind": "file", "path": source}] if source else []),
        "out_dir": out_dir or "",
        "status": "作業中", "memo": "", "due": "",
        "created": now(), "updated": now(),
    })
    return True

def meta_from_todo(html):
    todo = html + ".mt-todo.json"
    if os.path.exists(todo):
        try:
            j = json.load(open(todo, encoding="utf-8-sig"))
            return j.get("title"), j.get("source"), j.get("count")
        except Exception:
            pass
    return None, None, None

def ordered(projects):
    return sorted(projects, key=lambda p: p.get("updated", ""), reverse=True)

def file_uri(path):
    try:
        return Path(os.path.abspath(path)).as_uri()
    except Exception:
        return ""

ap = argparse.ArgumentParser()
ap.add_argument("cmd", choices=["add", "add-batch", "list", "get", "set-status",
                                 "set-memo", "set-due", "remove", "dashboard",
                                 "create", "add-source", "set-main-tm", "add-sub-tm",
                                 "new-tm", "show", "srcs", "subs", "undo-source",
                                 "undo-sub-tm", "set-outdir", "set-assignee",
                                 "set-product-tm", "run", "export", "idof", "serve",
                                 "reinsert-json"])
ap.add_argument("--store", default=DEFAULT_STORE)
ap.add_argument("--xliff", default="", help="reinsert-json: TEP で書き出した XLIFF")
ap.add_argument("--uidmap", default="", help="reinsert-json: tm_match_analysis が出した <html>.uidmap.json")
ap.add_argument("--confirmed-only", dest="confirmed_only", action="store_true",
                help="reinsert-json: 確定行(state=final/confirmed)のみ反映")
ap.add_argument("--term-store", dest="term_store", default="", help="用語集 TSV（全体共通・既定は Live_TM\\_terms.tsv）")
ap.add_argument("--html", default="")
ap.add_argument("--title", default=None)
ap.add_argument("--source", default=None)
ap.add_argument("--segs", type=int, default=None)
ap.add_argument("--mt", type=int, default=None)
ap.add_argument("--combined", default="")
ap.add_argument("--index", type=int, default=0)
ap.add_argument("--status", default="")
ap.add_argument("--memo", default=None)
ap.add_argument("--due", default=None)
ap.add_argument("--active", action="store_true", help="list: hide 完了")
ap.add_argument("--out", default="")
ap.add_argument("--delete-file", dest="delete_file", action="store_true")
ap.add_argument("--id", default="")
ap.add_argument("--name", default="")
ap.add_argument("--kind", default="file", help="add-source: file | dir")
ap.add_argument("--path", default="")
ap.add_argument("--assignee", default="")
# run: locate the engine/template/cache and (optionally) override the combined to-do path
ap.add_argument("--engine", default="", help="run: path to tm_match_analysis.py")
ap.add_argument("--template", default="", help="run: HTML template path")
ap.add_argument("--cache-dir", dest="cache_dir", default="", help="run: index cache folder")
ap.add_argument("--port", type=int, default=8765, help="serve: local HTTP port (auto-advances if busy)")
ap.add_argument("--mark-missing", dest="mark_missing", action="store_true",
                help="export: wrap untranslated sentences with 〔未訳〕")
a = ap.parse_args()

def find_by_id(projects, pid):
    for p in projects:
        if p.get("id") == pid:
            return p
    return None

def row_id(p):
    """Stable id for any ledger entry. Definitions/new artifacts carry a real 'id';
    legacy artifacts (registered before ids) get a deterministic id from their html path."""
    i = p.get("id")
    if i:
        return i
    import hashlib
    h = p.get("html", "")
    return ("art-" + hashlib.md5(ncase(h).encode("utf-8")).hexdigest()[:12]) if h else ""

def find_by_row_id(projects, rid):
    if not rid:
        return None
    for p in projects:
        if row_id(p) == rid:
            return p
    return None

def make_id(projects):
    base = "proj-" + datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    pid = base; k = 1
    while find_by_id(projects, pid):
        k += 1; pid = base + "-" + str(k)
    return pid

EMPTY_TMX = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<tmx version="1.4">\n'
             '  <header creationtool="Kotonoha" creationtoolversion="' + VERSION + '" segtype="sentence" '
             'o-tmf="Kotonoha" adminlang="en-US" srclang="en-US" datatype="plaintext"/>\n'
             '  <body>\n  </body>\n</tmx>\n')

# Native Windows "Open" dialog, run in a fresh subprocess (avoids Tk threading issues
# inside the HTTP server). Prints selected absolute path(s), newline-separated.
TK_PICK = r'''
import sys
try:
    import tkinter as tk
    from tkinter import filedialog as fd
except Exception:
    sys.stderr.write("NOTK"); sys.exit(2)
kind = sys.argv[1] if len(sys.argv) > 1 else "source"
multiple = len(sys.argv) > 2 and sys.argv[2] == "1"
root = tk.Tk(); root.withdraw()
try:
    root.attributes("-topmost", True); root.update()
except Exception:
    pass
if kind == "dir":
    res = fd.askdirectory(title="フォルダーを選択", mustexist=True)
    paths = [res] if res else []
else:
    FT = {
        "tmx":    ([("TMX", "*.tmx"), ("All files", "*.*")], "TM (.tmx) を選択"),
        "source": ([("MDX / MD", "*.mdx *.md"), ("All files", "*.*")], "ソース (.mdx / .md) を選択"),
        "xliff":  ([("XLIFF", "*.xliff *.xlf"), ("All files", "*.*")], "XLIFF を選択"),
        "html":   ([("HTML", "*.html *.htm"), ("All files", "*.*")], "HTML を選択"),
        "json":   ([("JSON / JSONL", "*.json *.jsonl"), ("All files", "*.*")], "JSON / JSONL を選択"),
    }
    ft, title = FT.get(kind, FT["source"])
    if multiple:
        res = fd.askopenfilenames(title=title, filetypes=ft)
        paths = list(root.tk.splitlist(res)) if res else []
    else:
        res = fd.askopenfilename(title=title, filetypes=ft)
        paths = [res] if res else []
sys.stdout.write("\n".join(paths))
'''

# Native "Save As" dialog for creating a new .tmx. Prints the chosen path (or empty if cancelled).
TK_SAVE_TMX = r'''
import sys
try:
    import tkinter as tk
    from tkinter import filedialog as fd
except Exception:
    sys.stderr.write("NOTK"); sys.exit(2)
root = tk.Tk(); root.withdraw()
try:
    root.attributes("-topmost", True); root.update()
except Exception:
    pass
res = fd.asksaveasfilename(title="新規メイン TM (.tmx) の保存先",
                          defaultextension=".tmx",
                          filetypes=[("TMX", "*.tmx"), ("All files", "*.*")])
sys.stdout.write(res or "")
'''


def create_project_full(projects, name, sources=None, main_tm="", product_tm="", sub_tms=None,
                         run_mt=True):
    """Create a definition in one shot (used by the serve API). Caller saves.
    run_mt: 既訳のない(≤74%)セグメントのMTを翻訳欄に反映するか（False=英語のまま・MTは履歴へ）。"""
    pid = make_id(projects)
    projects.append({
        "id": pid, "type": "project", "name": name or pid, "status": "未解析",
        "sources": [{"kind": (s.get("kind") or "file"), "path": s.get("path", "")}
                    for s in (sources or []) if s.get("path")],
        "main_tm": main_tm or "", "product_tm": product_tm or "",
        "sub_tms": [t for t in (sub_tms or []) if t],
        "run_mt": bool(run_mt),
        "created": now(), "updated": now(),
    })
    return pid


def expand_sources(srcs, dir_exts, log=print):
    """Expand a definition's sources into manifest entries [{src, rel}].
    Explicitly-added files are kept as-is (rel = basename stem); folders are walked
    recursively (only files ending in dir_exts) and rooted at the folder name so the
    internal hierarchy is preserved in the output (and two folders can't collide)."""
    entries = []; seen = set()
    def add_entry(src, rel):
        ab = os.path.abspath(src)
        if ab in seen or not os.path.isfile(src):
            return
        seen.add(ab); entries.append({"src": ab, "rel": rel.replace("\\", "/")})
    for s in (srcs or []):
        kind = s.get("kind", "file"); path = s.get("path", "")
        if kind == "dir":
            if not os.path.isdir(path):
                log("WARN: folder not found: %s" % path); continue
            root = os.path.basename(os.path.normpath(path)) or "src"
            for base, _dirs, files in os.walk(path):
                for fn in sorted(files):
                    if fn.lower().endswith(tuple(dir_exts)):
                        full = os.path.join(base, fn)
                        stem = os.path.splitext(os.path.relpath(full, path))[0]
                        add_entry(full, root + "/" + stem)
        else:
            if os.path.isfile(path):
                add_entry(path, os.path.splitext(os.path.basename(path))[0])
            else:
                log("WARN: file not found: %s" % path)
    return entries


def _first_source_path(p):
    """プロジェクトの最初のソースのパス（dict/str どちらにも対応）。無ければ p['source']。"""
    srcs = p.get("sources") or []
    if srcs:
        s0 = srcs[0]
        return (s0.get("path", "") if isinstance(s0, dict) else (s0 or "")) or ""
    return p.get("source", "") or ""


# プロジェクトの作業サブフォルダー（この名前のフォルダーの親をプロジェクトルートとみなす）
_WORK_SUBFOLDERS = {"1_en", "2_for review", "3_final", "_kotonoha", "_details"}


def project_root_for(path):
    """ソースのパスからプロジェクトフォルダー（親）を推定して返す。
    1_en / 2_For review / 3_Final / _kotonoha / _Details のような作業サブフォルダーが
    祖先にあれば、その親をプロジェクトルートとする。無ければソースの置かれたフォルダー。"""
    if not path:
        return ""
    path = os.path.abspath(path)
    probe = path if os.path.isdir(path) else os.path.dirname(path)
    base_dir = probe
    while True:
        if os.path.basename(probe).lower() in _WORK_SUBFOLDERS:
            return os.path.dirname(probe)
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    return base_dir


def details_dir_for(p, create=True):
    """中間生成物（作業ファイル・manifest・combined 等）の保存先を返す。
    = <プロジェクトルート>/_kotonoha（無ければ自動作成）。
    ソースが特定できない場合は従来の out_dir かフォールバック先。"""
    src0 = _first_source_path(p)
    if src0:
        root = project_root_for(src0)
    else:
        root = p.get("out_dir") or os.path.join(HERE, "..", "Kotonoha-out",
                                                 (p.get("name") or p.get("id") or "project"))
    det = os.path.join(root, "_kotonoha")
    if create:
        os.makedirs(det, exist_ok=True)
    return os.path.abspath(det)


def export_dest_for(p, out_path=""):
    """出力（翻訳版）の保存先。
    - out_path が絶対/区切り入りパス → そのフォルダー
    - out_path が単なる名前（例 "3_Final"）→ プロジェクトルート下のサブフォルダー
    - 未指定 → <ルート>/2_For review（既定）"""
    src0 = _first_source_path(p)
    root = project_root_for(src0) if src0 else (p.get("out_dir") or HERE)
    if out_path:
        if (os.sep in out_path) or ("/" in out_path) or (":" in out_path):
            d = os.path.abspath(out_path)
        else:
            d = os.path.join(root, out_path)
    else:
        d = os.path.join(root, "2_For review")
    os.makedirs(d, exist_ok=True)
    return os.path.abspath(d)


def run_project(projects, store, pid, out_path="", engine="", template="",
                cache_dir="", log=print, capture=False):
    """Analyze + Pre-translate a saved definition. Shared by the `run` CLI command
    and the serve API. Returns a result dict; registers produced articles and saves."""
    import subprocess
    p = find_by_id(projects, pid)
    if not p or not (p.get("main_tm") and p.get("sources")):
        return {"ok": False, "error": "実行可能なプロジェクト（ソース＋メインTM）が見つかりません: %s" % pid}
    srcs = p.get("sources", [])
    main_tm = p.get("main_tm", "")
    if not srcs:
        return {"ok": False, "error": "project has no sources"}
    if not main_tm or not os.path.exists(main_tm):
        return {"ok": False, "error": "main TM not found: %s" % (main_tm or "(未設定)")}

    entries = expand_sources(srcs, (".mdx", ".md"), log)
    if not entries:
        return {"ok": False, "error": "no .mdx/.md source files found under the project's sources"}

    # 中間生成物はプロジェクトフォルダー配下 <2_For review>/_Details に保存する
    out_dir = os.path.abspath(out_path) if out_path else details_dir_for(p)
    os.makedirs(out_dir, exist_ok=True)
    manifest = os.path.join(out_dir, "_sources.manifest.json")
    json.dump({"sources": entries}, open(manifest, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    combined = os.path.join(out_dir, "combined.mt-todo.json")
    engine = engine or os.path.join(HERE, "tm_match_analysis.py")
    template = template or os.path.join(HERE, "TM-Match-Explorer-demo.html")

    cmd = [sys.executable, engine, "--tmx", main_tm,
           "--source-manifest", manifest, "--template", template,
           "--out-dir", out_dir, "--combined-todo", combined,
           "--run-mt", ("1" if p.get("run_mt", True) else "0")]
    product_tm = p.get("product_tm", "")
    if product_tm:
        if os.path.exists(product_tm):
            cmd += ["--product-tmx", product_tm]
        else:
            log("WARN: Product TM not found (skipped): %s" % product_tm)
            product_tm = ""
    for st in p.get("sub_tms", []):
        if st:
            cmd += ["--sub-tmx", st]
    if cache_dir:
        cmd += ["--cache-dir", cache_dir]
    # サマリーのメタ情報用にプロジェクト名／詳細を渡す
    _pdetail = "状態: %s ／ ソース %d 件 ／ サブTM %d 件" % (
        (p.get("status") or "-"), len(entries), len(p.get("sub_tms", [])))
    if p.get("memo"):
        _pdetail += " ／ メモ: " + str(p.get("memo"))
    if p.get("due"):
        _pdetail += " ／ 期日: " + str(p.get("due"))
    cmd += ["--project-name", (p.get("name") or p.get("id") or ""), "--project-detail", _pdetail]

    log("プロジェクト「%s」: ソース %d 件 ／ メインTM 1 ／ Product TM %s ／ サブTM %d 件 → %s"
        % (p.get("name", ""), len(entries), ("有" if product_tm else "無"),
           len(p.get("sub_tms", [])), out_dir))
    out_text = ""
    if capture:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
        out_text = r.stdout or ""; rc = r.returncode
    else:
        rc = subprocess.call(cmd)
    if rc != 0:
        return {"ok": False, "error": "解析エンジンが異常終了しました (exit %d)" % rc,
                "rc": rc, "log": out_text}

    # 生成物（中間生成物）はプロジェクトに記録するだけ。別プロジェクトとして台帳に
    # 自動登録はしない（プロジェクトを作成するのはユーザーのみ）。
    artifacts = []
    produced = []   # 実行後にプロジェクト名タブで自動表示する作業ファイル（title+html）
    if os.path.exists(combined):
        data = json.load(open(combined, encoding="utf-8-sig"))
        for art in data.get("articles", []):
            htmlp = art.get("html", "")
            if not htmlp:
                continue
            # 再生成しても保存済みMT訳があれば自動で再反映（「実行」でMT反映が消えないように）
            md = htmlp + ".mt-done.jsonl"
            if os.path.isfile(htmlp) and os.path.isfile(md):
                try:
                    inject_mt_run(mode="single", html=htmlp, mt=md, capture=True)
                    log("  MT再反映: %s" % os.path.basename(md))
                except Exception as _e:
                    log("  WARN: MT再反映に失敗: %s" % _e)
            rec = {"title": art.get("title", ""), "html": htmlp,
                   "source": art.get("source", ""),
                   "segs": art.get("segs"), "mt": art.get("mt")}
            artifacts.append(rec)
            if art.get("title"):
                produced.append({"title": art.get("title"), "html": htmlp})
    p["artifacts"] = artifacts
    if p.get("status") in (None, "", "未解析"):
        p["status"] = "作業中"
    p["out_dir"] = out_dir; p["combined"] = combined
    p["last_run"] = now(); p["updated"] = now()
    save(store, projects)
    return {"ok": True, "out_dir": out_dir, "combined": combined,
            "registered": len(artifacts), "produced": produced,
            "project": (p.get("name") or p.get("id")), "log": out_text}


def _balanced_end(s, j):
    """s[j]=='[' として、対応する ']' の位置を返す（文字列リテラル内の括弧は無視）。"""
    depth = 0; k = j; instr = False; esc = False; q = ''
    while k < len(s):
        c = s[k]
        if instr:
            if esc: esc = False
            elif c == '\\': esc = True
            elif c == q: instr = False
        else:
            if c == '"' or c == "'": instr = True; q = c
            elif c == '[': depth += 1
            elif c == ']':
                depth -= 1
                if depth == 0: return k
        k += 1
    return -1

def _seg_from_html(html):
    i = html.find("const SEG = [")
    if i < 0: return None
    j = html.find("[", i); e = _balanced_end(html, j)
    if e < 0: return None
    try:
        return json.loads(html[j:e + 1])
    except Exception:
        return None

def export_json_from_tep(art, out_path, store):
    """JSON記事の『出力』: 記事の訳文（Pre-translation の結果＋MT＋保存済み編集）を
    uidmap 経由で元 JSON に適用し、翻訳済み JSON を出力（TMの再照合はしない）。
    art は生成物 dict（html/title/source）。"""
    import json_io
    html = art.get("html", "")
    if not (html and os.path.isfile(html)):
        return {"ok": False, "error": "作業ファイル(HTML)が見つかりません"}
    uidmap = html + ".uidmap.json"
    if not os.path.isfile(uidmap):
        return {"ok": False, "error": "uidmap が見つかりません: %s" % uidmap}
    m = json.load(open(uidmap, encoding="utf-8-sig"))
    uids = m.get("uids", [])
    jpath = m.get("json", "") or art.get("source", "")
    if not (jpath and os.path.isfile(jpath)):
        return {"ok": False, "error": "元 JSON が見つかりません: %s" % jpath}
    seg = _seg_from_html(open(html, encoding="utf-8").read())
    if seg is None:
        return {"ok": False, "error": "作業ファイルからSEGを取得できません"}
    # 保存済み編集（_wip）をオーバーレイ（記事名＝TEPのタイトルでキー化）
    edits = {}
    try:
        safe = ("".join(("_" if c in '\\/:*?"<>|' else c) for c in (art.get("title") or ""))[:120]) or "untitled"
        wip = os.path.join(os.path.dirname(os.path.abspath(store)), "_wip", safe + ".json")
        if os.path.isfile(wip):
            edits = (json.load(open(wip, encoding="utf-8")).get("edits") or {})
    except Exception:
        edits = {}
    def plain_ja(s):
        return "".join(t for op, t in (s.get("ja") or []) if op != "del")
    trans = {}; applied = 0
    for i, uid in enumerate(uids):
        if i >= len(seg):
            break
        txt = edits.get(str(i))
        if txt is None:
            txt = plain_ja(seg[i])
        if txt and txt.strip():
            trans[uid] = txt; applied += 1
    if not trans:
        return {"ok": False, "error": "適用できる訳がありません"}
    try:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    except Exception:
        pass
    res = json_io.apply(jpath, out_path, trans)
    return {"ok": True, "out": out_path, "applied": applied,
            "filled": (res.get("filled") if isinstance(res, dict) else None)}


def export_project(projects, store, pid, out_path="", cache_dir="",
                   mark_missing=False, log=print, capture=False):
    """Round-trip output: apply the definition's TM(s) to its sources and write a
    translated copy IN THE ORIGINAL FORMAT (via doc_export.py / doc_io). Run after
    pre-translation + MT + TEP writeback so the TM covers the content. Shared by the
    `export` CLI command and the serve API."""
    import subprocess
    p = find_by_id(projects, pid)
    if not p or not (p.get("main_tm") and p.get("sources")):
        return {"ok": False, "error": "実行可能なプロジェクト（ソース＋メインTM）が見つかりません: %s" % pid}
    main_tm = p.get("main_tm", "")
    if not main_tm or not os.path.exists(main_tm):
        return {"ok": False, "error": "main TM not found: %s" % (main_tm or "(未設定)")}
    try:
        import doc_io
        exts = tuple(doc_io.supported_exts())
    except Exception:
        exts = (".txt",)
    entries = expand_sources(p.get("sources", []), exts, log)
    if not entries:
        return {"ok": False, "error": "no exportable source files (対応形式: %s)" % " ".join(exts)}

    # 出力（翻訳版）の保存先: 選択可能（2_For review / 3_Final / 任意）。既定は 2_For review。
    dest = export_dest_for(p, out_path)
    # 中間生成物（manifest 等）は常に _Details に置く
    det = details_dir_for(p)

    # JSON記事: TMの再照合ではなく、記事の訳文（Pre-translation の結果＋MT＋編集）を直接適用して100%出力
    arts = list(p.get("artifacts") or [])
    if not arts and p.get("html"):
        arts = [{"title": p.get("title", ""), "html": p.get("html", ""), "source": p.get("source", "")}]
    json_arts = [a for a in arts
                 if a.get("html") and os.path.isfile(a["html"])
                 and os.path.isfile(a["html"] + ".uidmap.json")
                 and (a.get("source", "") or "").lower().endswith(".json")]
    if json_arts:
        outs = []; total = 0; errs = []
        for a in json_arts:
            base = os.path.basename(a.get("source", "") or ((a.get("title", "") or "translated") + ".json"))
            outp = os.path.join(dest, base)
            res = export_json_from_tep(a, outp, store)
            if res.get("ok"):
                total += (res.get("applied") or 0); outs.append(outp)
                log("JSON『%s』: 記事の訳文を適用して出力 → %s（適用 %d）"
                    % (a.get("title", ""), outp, res.get("applied", 0)))
            else:
                errs.append("%s: %s" % (a.get("title", ""), res.get("error")))
                log("WARN: 出力失敗 %s: %s" % (a.get("title", ""), res.get("error")))
        if outs:
            return {"ok": True, "out_dir": dest, "out": outs[0], "outs": outs,
                    "applied": total, "mode": "tep", "log": ""}
        log("WARN: 記事の訳文からの出力に失敗、TM方式にフォールバック: %s" % "; ".join(errs))

    out_dir = det
    manifest = os.path.join(out_dir, "_export.manifest.json")
    json.dump({"sources": entries}, open(manifest, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    exporter = os.path.join(HERE, "doc_export.py")
    cmd = [sys.executable, exporter, "--source-manifest", manifest,
           "--tmx", main_tm, "--out-dir", dest]
    subs = [st for st in p.get("sub_tms", []) if st]
    if subs:
        cmd += ["--sub-tmx"] + subs          # one flag, all paths (nargs="*")
    if cache_dir:
        cmd += ["--cache-dir", cache_dir]
    if mark_missing:
        cmd += ["--mark-missing"]

    log("プロジェクト「%s」: 元形式で翻訳版を出力 → %s"
        % (p.get("name", ""), os.path.join(dest, "translated")))
    out_text = ""
    if capture:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
        out_text = r.stdout or ""; rc = r.returncode
    else:
        rc = subprocess.call(cmd)
    if rc != 0:
        return {"ok": False, "error": "出力に失敗しました (exit %d)" % rc, "rc": rc, "log": out_text}
    return {"ok": True, "out_dir": os.path.join(dest, "translated"), "log": out_text}


def project_details(projects, pid):
    """『詳細』パネル用: 作業サマリー＋_Details（中間生成物）フォルダーの一覧を返す。"""
    import datetime as _dt
    p = find_by_id(projects, pid)
    if not p:
        return {"ok": False, "error": "project not found"}
    det = details_dir_for(p, create=False)
    root = os.path.dirname(det)         # プロジェクトルート（_kotonoha の親）
    rev = os.path.join(root, "2_For review")
    arts = p.get("artifacts") or []
    art_html = set(os.path.abspath(a.get("html", "")) for a in arts if a.get("html"))
    files = []
    if os.path.isdir(det):
        for nm in sorted(os.listdir(det)):
            fp = os.path.join(det, nm)
            if not os.path.isfile(fp):
                continue
            rec = {"name": nm, "path": fp,
                   "is_tep": (nm.lower().endswith(".html") and os.path.abspath(fp) in art_html)}
            try:
                st = os.stat(fp)
                rec["size"] = st.st_size
                rec["mtime"] = _dt.datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
            except Exception:
                pass
            files.append(rec)
    summary = {
        "name": p.get("name") or p.get("id") or "",
        "status": p.get("status", ""),
        "sources": len(p.get("sources") or []),
        "main_tm": os.path.basename(p.get("main_tm", "")),
        "product_tm": bool(p.get("product_tm")),
        "sub_tms": len(p.get("sub_tms") or []),
        "last_run": p.get("last_run", ""),
        "updated": p.get("updated", ""),
        "artifacts": [{"title": a.get("title", ""), "html": a.get("html", ""),
                       "segs": a.get("segs"), "mt": a.get("mt")} for a in arts],
    }
    return {"ok": True, "project_root": root, "review_dir": rev, "details_dir": det,
            "exists": os.path.isdir(det), "summary": summary, "files": files}


# ===== TM タブ: プロジェクトが使用する TM を列挙（編集は書込可能TMのみ許可） =====
_TM_EDIT_MAXSIZE = 60 * 1024 * 1024   # これ以上大きいTMは編集対象外（巨大XTM保護）

def _tm_editable(path, size):
    """書込可能TMか: XTM（読み取り専用コーパス）配下でなく、サイズが閾値未満。"""
    p = (path or "").replace("\\", "/").lower()
    if "/xtm/" in p:
        return False
    return 0 < size < _TM_EDIT_MAXSIZE

def tm_list_rows(projects, with_count=True):
    """台帳の全プロジェクトが参照する TM（メイン/サブ/Product）を一覧化。"""
    import tm_io
    seen = set(); rows = []
    def add(path, role):
        if not path:
            return
        ap = os.path.abspath(path)
        key = ap.lower()
        if key in seen:
            return
        seen.add(key)
        exists = os.path.isfile(ap)
        size = (os.path.getsize(ap) if exists else 0)
        editable = exists and _tm_editable(ap, size)
        cnt = (tm_io.count(ap) if (editable and with_count) else None)
        rows.append({"path": ap, "name": os.path.basename(ap), "role": role,
                     "exists": exists, "size": size, "editable": editable, "count": cnt})
    for p in projects:
        add(p.get("main_tm", ""), "メインTM")
        add(p.get("product_tm", ""), "Product TM")
        for st in (p.get("sub_tms") or []):
            add(st, "サブTM")
    return rows

def _tm_known_paths(projects):
    return set(r["path"].lower() for r in tm_list_rows(projects, with_count=False))

def _conc_cache_dir():
    """Concordance キャッシュ置き場（索引キャッシュと同じ TM 管理 Index フォルダー）。
    リポジトリ/同期対象外なので巨大な pkl を置いても問題ない。"""
    try:
        c = read_cfg().get("CACHE", "")
    except Exception:
        c = ""
    if c:
        return c
    return os.path.join(r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production"
                        r"\TM manaegment\TM\___Working", "Kotonoha", "Index")


# ===== 台帳フィールド操作（pid ベース・serve API 用。CLI は --index 版を別に持つ） =====
def update_field(projects, store, pid, field, value):
    """Set one ledger field (status/memo/due) on the project with this id, then save."""
    p = find_by_row_id(projects, pid)
    if not p:
        return {"ok": False, "error": "project not found: %s" % pid}
    p[field] = value or ""
    p["updated"] = now()
    save(store, projects)
    return {"ok": True, "field": field, "value": p[field]}


def remove_project(projects, store, pid, delete_file=False):
    """Remove the project with this id (optionally its artifact HTML + mt-todo), then save."""
    p = find_by_row_id(projects, pid)
    if not p:
        return {"ok": False, "error": "project not found: %s" % pid}
    deleted = []
    if delete_file:
        for f in (p.get("html", ""), p.get("html", "") + ".mt-todo.json"):
            try:
                if f and os.path.exists(f):
                    os.remove(f); deleted.append(f)
            except Exception:
                pass
    projects[:] = [x for x in projects if x is not p]   # keep same list object
    save(store, projects)
    return {"ok": True, "deleted": deleted}


# ===== 補助スクリプト呼び出し（export_project と同じ subprocess 方式。capture で stdout を返す） =====
def _run_script(cmd, capture=False, cwd=None):
    import subprocess
    if capture:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace", cwd=cwd)
        return r.returncode, (r.stdout or "")
    return subprocess.call(cmd, cwd=cwd), ""


# ===== ハブ統合: 別ツール（File Comparison / JA Version Check）を subprocess で実行 =====
FILECOMPARE_SCRIPT = os.path.join(HERE, "..", "File comparison", "EN_comp", "Beta1", "file_compare_fullset.py")
VERSIONCHECK_SCRIPT = os.path.join(HERE, "..", "File comparison", "JA_comp", "ja_version_check.py")

def filecompare_run(target="", current="", results="", label="", translatable_only=False, capture=True):
    """EN ファイル比較（file_compare_fullset.py）。Target 翻訳済みフォルダー vs Current。"""
    script = os.path.abspath(FILECOMPARE_SCRIPT)
    if not os.path.exists(script):
        return {"ok": False, "error": "file_compare_fullset.py が見つかりません: %s" % script}
    cmd = [sys.executable, script]
    if target:
        cmd.append(target)
    if current:
        cmd += ["--current", current]
    if results:
        cmd += ["--results", results]
    if label:
        cmd += ["--label", label]
    if translatable_only:
        cmd.append("--translatable-only")
    rc, out = _run_script(cmd, capture=True, cwd=os.path.dirname(script))
    return {"ok": rc == 0, "log": out, "reveal": (results or ""), "error": ("" if rc == 0 else "exit %d" % rc)}

def versioncheck_run(en="", ja="", published="", results="", no_tm=False, capture=True):
    """JA バージョンチェック（ja_version_check.py）。EN/JA フォルダーを比較。"""
    script = os.path.abspath(VERSIONCHECK_SCRIPT)
    if not os.path.exists(script):
        return {"ok": False, "error": "ja_version_check.py が見つかりません: %s" % script}
    cmd = [sys.executable, script]
    if en:
        cmd += ["--en", en]
    if ja:
        cmd += ["--ja", ja]
    if published:
        cmd += ["--published", published]
    if results:
        cmd += ["--results", results]
    if no_tm:
        cmd.append("--no-tm")
    rc, out = _run_script(cmd, capture=True, cwd=os.path.dirname(script))
    return {"ok": rc == 0, "log": out, "reveal": (results or ""), "error": ("" if rc == 0 else "exit %d" % rc)}


def inject_mt_run(mode="single", html="", mt="", combined_todo="", combined_mt="", capture=False):
    """MTをHTMLに反映（inject_mt.py）。mode='single'（html+mt）/ 'batch'（combined-todo+combined-mt）。"""
    script = os.path.join(HERE, "inject_mt.py")
    if mode == "batch":
        if not (combined_todo and os.path.exists(combined_todo)):
            return {"ok": False, "error": "combined.mt-todo.json が見つかりません"}
        if not (combined_mt and os.path.exists(combined_mt)):
            return {"ok": False, "error": "combined.mt-done.jsonl が見つかりません"}
        cmd = [sys.executable, script, "--combined-todo", combined_todo, "--combined-mt", combined_mt]
    else:
        if not (html and os.path.exists(html)):
            return {"ok": False, "error": "HTML が見つかりません"}
        if not (mt and os.path.exists(mt)):
            return {"ok": False, "error": "mt-done ファイルが見つかりません"}
        cmd = [sys.executable, script, "--html", html, "--mt", mt]
    rc, out = _run_script(cmd, capture)
    if rc != 0:
        return {"ok": False, "error": "MTの反映に失敗しました (exit %d)" % rc, "rc": rc, "log": out}
    return {"ok": True, "log": out}


def prebuild_index(univ="", prod="", cache_dir="", rebuild=False, capture=False):
    """索引キャッシュを事前作成。tm_index を import して load_or_build を直接呼ぶ
    （tm_index.py を __main__ 実行すると Index が pickle できずキャッシュ保存に失敗する既知事象を回避）。
    数分かかる場合あり（同期）。"""
    if not (univ and os.path.exists(univ)):
        return {"ok": False, "error": "University TMX が見つかりません"}
    if not cache_dir:
        return {"ok": False, "error": "索引キャッシュ フォルダーが指定されていません"}
    try:
        import tm_index
    except Exception as e:
        return {"ok": False, "error": "tm_index を読み込めません: %s" % e}
    specs = [(univ, False)]
    if prod and os.path.exists(prod):
        specs.append((prod, True))
    logs = []
    def _log(*a):
        logs.append(" ".join(str(x) for x in a))
    try:
        idx = tm_index.load_or_build(specs, cache_dir, rebuild=rebuild, log=_log)
    except Exception as e:
        return {"ok": False, "error": "索引作成に失敗しました: %s" % e, "log": "\n".join(logs)}
    logs.append("ready. keys: %d product terms: %d" % (len(idx.keys), len(idx.product_terms)))
    return {"ok": True, "keys": len(idx.keys), "product_terms": len(idx.product_terms),
            "log": "\n".join(logs)}


def writeback_run(xliff=None, xliff_dir="", master="", project_tmx="", customer="",
                  dry_run=True, backup=True, capture=False):
    """TEP 確定行を TM へ書き戻す（tm_writeback.py）。本実行(dry_run=False)の直前に書込先 TMX を日付きバックアップ。"""
    import shutil, time as _time
    script = os.path.join(HERE, "tm_writeback.py")
    xliff = [x for x in (xliff or []) if x]
    if not xliff and not xliff_dir:
        return {"ok": False, "error": "XLIFF ファイルまたはフォルダーを指定してください"}
    backed = []
    if backup and not dry_run:
        ts = _time.strftime("%Y%m%d-%H%M%S")
        for t in (master, project_tmx):
            if t and os.path.exists(t):
                base, ext = os.path.splitext(t)
                bak = "%s.bak_%s%s" % (base, ts, ext or ".tmx")
                try:
                    shutil.copy2(t, bak); backed.append(bak)
                except Exception as e:
                    return {"ok": False, "error": "バックアップに失敗したため中止しました: %s" % e}
    cmd = [sys.executable, script]
    if xliff:
        cmd += ["--xliff"] + xliff
    if xliff_dir:
        cmd += ["--xliff-dir", xliff_dir]
    if master:
        cmd += ["--master", master]
    if project_tmx:
        cmd += ["--project-tmx", project_tmx]
    if customer:
        cmd += ["--customer", customer]
    if dry_run:
        cmd += ["--dry-run"]
    rc, out = _run_script(cmd, capture)
    if rc != 0:
        return {"ok": False, "error": "書き戻しに失敗しました (exit %d)" % rc, "rc": rc, "log": out}
    return {"ok": True, "dry_run": bool(dry_run), "backed_up": backed, "log": out}


def glossary_run(source=None, source_dir="", html=None, xliff=None, xliff_dir="",
                 confirmed_only=False, tmx="", product_tmx="", cache_dir="", out="", capture=False):
    """UI Glossary を作成（ui_glossary.py）。<out>.csv / <out>.json を出力。"""
    script = os.path.join(HERE, "ui_glossary.py")
    source = [s for s in (source or []) if s]
    html = [h for h in (html or []) if h]
    xliff = [x for x in (xliff or []) if x]
    if not (source or source_dir or html or xliff or xliff_dir):
        return {"ok": False, "error": "ソース/HTML/XLIFF のいずれかを1つ以上指定してください"}
    if not out:
        return {"ok": False, "error": "出力プレフィックスを指定してください"}
    cmd = [sys.executable, script, "--out", out]
    if cache_dir:
        cmd += ["--cache-dir", cache_dir]
    if source:
        cmd += ["--source"] + source
    if source_dir:
        cmd += ["--source-dir", source_dir]
    if html:
        cmd += ["--html"] + html
    if xliff:
        cmd += ["--xliff"] + xliff
    if xliff_dir:
        cmd += ["--xliff-dir", xliff_dir]
    if confirmed_only:
        cmd += ["--confirmed-only"]
    if tmx and os.path.exists(tmx):
        cmd += ["--tmx", tmx]
    if product_tmx and os.path.exists(product_tmx):
        cmd += ["--product-tmx", product_tmx]
    rc, out_text = _run_script(cmd, capture)
    if rc != 0:
        return {"ok": False, "error": "Glossary 作成に失敗しました (exit %d)" % rc, "rc": rc, "log": out_text}
    return {"ok": True, "out": out, "csv": out + ".csv", "json": out + ".json", "log": out_text}


def reinsert_json(xliff_path, uidmap_path, out_path, json_path="", confirmed_only=False):
    """TEP で書き出した XLIFF の訳を uidmap 経由で元 JSON に適用し、翻訳済み JSON を出力。
    XLIFF trans-unit id(=セグメント index+1) → uid → json_io.apply。"""
    import json_io, xml.etree.ElementTree as ET
    if not (uidmap_path and os.path.exists(uidmap_path)):
        return {"ok": False, "error": "uidmap が見つかりません: %s" % uidmap_path}
    m = json.load(open(uidmap_path, encoding="utf-8-sig"))
    uids = m.get("uids", [])
    jpath = json_path or m.get("json", "")
    if not (jpath and os.path.exists(jpath)):
        return {"ok": False, "error": "元 JSON が見つかりません: %s" % jpath}
    if not (xliff_path and os.path.exists(xliff_path)):
        return {"ok": False, "error": "XLIFF が見つかりません: %s" % xliff_path}
    strip = lambda t: t.split("}")[-1]
    root = ET.parse(xliff_path).getroot()
    trans = {}; applied = 0
    for tu in root.iter():
        if strip(tu.tag) != "trans-unit":
            continue
        tid = tu.attrib.get("id", "")
        tgt = None; state = ""; note = ""
        for ch in tu:
            ct = strip(ch.tag)
            if ct == "target":
                tgt = "".join(ch.itertext()); state = ch.attrib.get("state", "")
            elif ct == "note":
                note = "".join(ch.itertext())
        if tgt is None:
            continue
        if confirmed_only and not (state == "final" or "confirmed" in note.lower()):
            continue
        try:
            idx = int(tid) - 1
        except ValueError:
            continue
        if 0 <= idx < len(uids) and tgt.strip():
            trans[uids[idx]] = tgt; applied += 1
    if not trans:
        return {"ok": False, "error": "XLIFF から適用できる訳がありません（確定行なし？）"}
    res = json_io.apply(jpath, out_path, trans)
    return {"ok": True, "out": out_path, "applied": applied, "filled": res.get("filled")}


def read_cfg():
    """Read _paths.cfg (KEY=VALUE, # comments) next to this script into a dict."""
    cfg = os.path.join(HERE, "_paths.cfg"); d = {}
    if os.path.exists(cfg):
        try:
            for line in open(cfg, encoding="utf-8-sig"):
                line = line.strip()
                if line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1); d[k.strip()] = v.strip()
        except Exception:
            pass
    return d


def build_rows(projects, served=False):
    """Row dicts for the dashboard table and the /api/projects endpoint (same shape).
    served=True のとき成果物の『開く』URI を同一オリジンの /article?id=… にする
    （編集画面をサーバー配信＝用語ペインのライブ連動を可能にするため）。"""
    cache = read_cfg().get("CACHE", "")
    pyexe = os.path.join(HERE, "projects.py")
    def _q(s):
        return ('"%s"' % s) if (s and " " in s) else s
    def run_cmd(pid):
        parts = ["python", _q(pyexe), "run", "--id", pid]
        if cache:
            parts += ["--cache-dir", _q(cache)]
        return " ".join(parts)
    rows = []
    for i, p in enumerate(ordered(projects), 1):
        is_def = p.get("type") == "project"
        runnable = bool(p.get("main_tm") and p.get("sources"))   # 定義でも記事でも、レシピがあれば実行/出力可
        if is_def:
            src = "ソース %d 件 ／ メインTM %s ／ Product %s ／ サブTM %d 件" % (
                len(p.get("sources", [])),
                (os.path.basename(p.get("main_tm", "")) or "未設定"),
                ("有" if p.get("product_tm") else "無"),
                len(p.get("sub_tms", [])))
        else:
            src = p.get("source", "")
        rows.append({
            "n": i, "title": (p.get("title") or p.get("name") or ""), "status": p.get("status", ""),
            "project": p.get("project", ""),
            "segs": p.get("segs"), "mt": p.get("mt"), "memo": p.get("memo", ""),
            "due": p.get("due", ""), "updated": p.get("updated", ""),
            "source": src,
            "uri": (("/article?id=" + row_id(p)) if (served and p.get("html"))
                    else (file_uri(p.get("html", "")) if p.get("html") else "")),
            "id": row_id(p),
            "pid": (p.get("id", "") if runnable else ""),
            "cmd": (run_cmd(p.get("id", "")) if runnable else ""),
        })
    return rows


projects = load(a.store)

def dashboard_html(projects, served=False, token=""):
    cols = [("n", "#", 48), ("title", "タイトル", 260), ("status", "状態", 100),
            ("segmt", "seg / MT", 90), ("due", "期日", 108), ("memo", "メモ", 220),
            ("updated", "更新", 128)]
    data = json.dumps(build_rows(projects, served=served), ensure_ascii=False)
    colmeta = json.dumps([{"id": c[0], "label": c[1], "w": c[2]} for c in cols], ensure_ascii=False)
    ktcfg = json.dumps({"served": bool(served), "token": token or ""}, ensure_ascii=False)
    tpl = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kotonoha プロジェクト一覧 (__VER__)</title>
<style>
:root{--bg:#F5F6F8;--card:#fff;--ink:#1B1F27;--muted:#5C6470;--line:#E4E7EC;--accent:#146C82;
--work:#B77C1F;--work-bg:#F6ECD8;--rev:#146C82;--rev-bg:#E4F0F3;--done:#2E9E6B;--done-bg:#E4F3EC;}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#101319;--card:#191D25;--ink:#E9EBEF;--muted:#9BA3AF;--line:#2A303A;--accent:#48AEC6;--work:#D6A24A;--work-bg:#33280f80;--rev:#48AEC6;--rev-bg:#17303880;--done:#4CB985;--done-bg:#15302480;}}
:root[data-theme=dark]{--bg:#101319;--card:#191D25;--ink:#E9EBEF;--muted:#9BA3AF;--line:#2A303A;--accent:#48AEC6;--work:#D6A24A;--work-bg:#33280f80;--rev:#48AEC6;--rev-bg:#17303880;--done:#4CB985;--done-bg:#15302480;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI","Noto Sans JP",system-ui,sans-serif;line-height:1.5}
.wrap{max-width:none;margin:0;padding:8px clamp(8px,1.2vw,16px) 36px}
body.served .wrap{padding-top:4px}
h1{font-size:22px;margin:.2em 0}.sub{color:var(--muted);font-size:13px;margin-bottom:16px}
.ctl{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0}
.ctl input[type=search]{flex:1;min-width:180px;padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--ink)}
.chip{border:1px solid var(--line);background:var(--card);color:var(--muted);border-radius:999px;padding:6px 11px;font-size:13px;cursor:pointer}
.chip[aria-pressed=true]{background:var(--ink);color:var(--bg);border-color:var(--ink)}
.toggle{font-size:13px;color:var(--muted);display:inline-flex;gap:6px;align-items:center;cursor:pointer}
.colmenu{position:relative}
#colbtn{border:1px solid var(--line);background:var(--card);color:var(--muted);border-radius:8px;padding:6px 11px;font-size:13px;cursor:pointer}
#colpanel{position:absolute;z-index:20;top:116%;right:0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:8px 12px;box-shadow:0 8px 24px rgba(0,0,0,.18);min-width:150px}
#colpanel label{display:block;font-size:13px;color:var(--ink);padding:4px 0;white-space:nowrap;cursor:pointer}
.toolspanel{position:absolute;z-index:20;top:116%;right:0;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px;box-shadow:0 8px 24px rgba(0,0,0,.18);min-width:200px}
.toolspanel button{display:block;width:100%;text-align:left;border:none;background:transparent;color:var(--ink);padding:8px 10px;border-radius:6px;font-size:13px;cursor:pointer;white-space:nowrap}
.toolspanel button:hover{background:color-mix(in srgb,var(--card),var(--ink) 8%)}
.fld select,.fld textarea{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);width:100%}
.fld textarea{min-height:68px;font-family:inherit}
.edit{display:inline-block;margin-left:5px;background:transparent;color:var(--muted);border:1px solid var(--line);padding:5px 10px;border-radius:8px;font-size:13px;font-weight:600;white-space:nowrap;cursor:pointer}
.edit:hover{border-color:var(--accent);color:var(--accent)}
.pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:12px;max-height:38vh;overflow:auto;font-family:Consolas,"Courier New",monospace;color:var(--ink)}
.toggle2{display:inline-flex;gap:7px;align-items:center;font-size:13px;color:var(--ink);cursor:pointer}
.btn{border:1px solid var(--line);background:var(--card);color:var(--muted);border-radius:8px;padding:6px 11px;font-size:13px;cursor:pointer}
.btn:hover{color:var(--ink);border-color:var(--accent)}
.btn[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.new{background:var(--accent);color:#fff;border-color:var(--accent);font-weight:600}
.note{background:var(--card);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:8px;padding:10px 12px;color:var(--ink);font-size:13px;margin:0 0 12px}
#ptable.locked th{cursor:default}
#ptable.locked th .rz{display:none}
.themebtn{margin-left:auto;border:1px solid var(--line);background:var(--card);color:var(--muted);border-radius:8px;padding:6px 10px;cursor:pointer}
.tablewrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px;background:var(--card)}
table{table-layout:fixed;width:100%;border-collapse:collapse}
th,td{padding:10px 12px;border-bottom:1px solid var(--line);border-right:1px solid var(--line);text-align:left;font-size:14px;vertical-align:top;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
th:last-child,td:last-child{border-right:none}
tbody tr:hover td{background:color-mix(in srgb,var(--card),var(--ink) 4%)}
th{position:relative;background:color-mix(in srgb,var(--card),var(--ink) 5%);font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;user-select:none}
tr:last-child td{border-bottom:none}
td.ti,td.memo{white-space:normal;word-break:break-word}
th{cursor:grab}
th.dragover{outline:2px dashed var(--accent);outline-offset:-2px}
th.act,td.act{position:sticky;right:0;overflow:visible;text-align:center;background:var(--card);box-shadow:-8px 0 8px -8px rgba(0,0,0,.25);cursor:default}
th.act{background:color-mix(in srgb,var(--card),var(--ink) 5%)}
th .rz{position:absolute;top:0;right:-3px;width:8px;height:100%;cursor:col-resize;z-index:5}
th .rz:hover{background:var(--accent);opacity:.35}
.badge{display:inline-block;font-size:12px;font-weight:600;padding:2px 9px;border-radius:999px;border:1px solid}
.b-work{color:var(--work);background:var(--work-bg);border-color:var(--work)}
.b-rev{color:var(--rev);background:var(--rev-bg);border-color:var(--rev)}
.b-done{color:var(--done);background:var(--done-bg);border-color:var(--done)}
.b-todo{color:var(--muted);background:transparent;border-color:var(--line)}
.n{color:var(--muted);font-variant-numeric:tabular-nums}
.open{display:inline-block;background:var(--accent);color:#fff;text-decoration:none;padding:6px 12px;border-radius:8px;font-size:13px;font-weight:600;white-space:nowrap}
.run{display:inline-block;background:transparent;color:var(--accent);border:1px solid var(--accent);padding:5px 11px;border-radius:8px;font-size:13px;font-weight:600;white-space:nowrap;cursor:pointer}
.run:hover{background:var(--accent);color:#fff}
.run:disabled,.exp:disabled{opacity:.55;cursor:default}
.exp{display:inline-block;margin-left:5px;background:transparent;color:var(--done);border:1px solid var(--done);padding:5px 10px;border-radius:8px;font-size:13px;font-weight:600;white-space:nowrap;cursor:pointer}
.exp:hover{background:var(--done);color:#fff}
.det{display:inline-block;margin-left:5px;background:transparent;color:var(--muted);border:1px solid var(--line);padding:5px 10px;border-radius:8px;font-size:13px;font-weight:600;white-space:nowrap;cursor:pointer}
.det:hover{border-color:var(--accent);color:var(--accent)}
.det[aria-pressed=true]{background:var(--accent);color:#fff;border-color:var(--accent)}
tr.detrow td{background:var(--bg);padding:0;border-right:none}
.detpanel{white-space:normal;padding:14px 16px;font-size:13px;color:var(--ink)}
.detpanel h3{font-size:14px;margin:0 0 8px}
.detpanel .sumline{color:var(--muted);margin:0 0 12px;line-height:1.7}
.detpanel .sumline b{color:var(--ink);font-weight:600}
.detpanel .dpath{font-family:Consolas,"Courier New",monospace;font-size:12px;color:var(--muted);word-break:break-all}
.detpanel .flist{border:1px solid var(--line);border-radius:8px;background:var(--card);overflow:hidden}
.detpanel .frow{display:flex;align-items:center;gap:10px;padding:8px 12px;border-bottom:1px solid var(--line)}
.detpanel .frow:last-child{border-bottom:none}
.detpanel .frow .fn{flex:1;min-width:0;word-break:break-all}
.detpanel .frow .fm{color:var(--muted);font-size:12px;white-space:nowrap}
.detpanel .frow .tep{color:var(--accent);font-weight:600;cursor:pointer;text-decoration:none}
.detpanel .frow .reveal{color:var(--muted);cursor:pointer;text-decoration:none;font-size:12px;white-space:nowrap}
.detpanel .frow .tep:hover,.detpanel .frow .reveal:hover{text-decoration:underline;color:var(--accent)}
.detpanel .ebar{display:flex;gap:8px;align-items:center;margin:0 0 10px;flex-wrap:wrap}
.detpanel .ebar button{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:8px;padding:5px 11px;font-size:13px;cursor:pointer}
.detpanel .ebar button:hover{border-color:var(--accent);color:var(--accent)}
.detpanel .empty{color:var(--muted);padding:10px 0}
#toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(12px);background:var(--ink);color:var(--bg);padding:10px 16px;border-radius:10px;font-size:13px;max-width:min(92vw,640px);box-shadow:0 8px 24px rgba(0,0,0,.3);opacity:0;pointer-events:none;transition:opacity .18s,transform .18s;z-index:50}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.srvbadge{display:none;font-size:12px;font-weight:600;color:#fff;background:var(--done);border-radius:999px;padding:3px 10px;margin-left:10px;vertical-align:middle}
body.served .srvbadge{display:inline-block}
.verbadge{font-size:12px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:2px 9px;margin-left:8px;vertical-align:middle}
.ovl{position:fixed;inset:0;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;z-index:60;padding:16px}
.modal{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:12px;max-width:720px;width:100%;max-height:88vh;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.modal h2{font-size:17px;margin:0;padding:16px 18px;border-bottom:1px solid var(--line)}
.modal .bd{padding:16px 18px;display:flex;flex-direction:column;gap:14px;overflow:auto}
.modal .ft{padding:14px 18px;border-top:1px solid var(--line);display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
.fld{display:flex;flex-direction:column;gap:6px}
.fld>label{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.fld input[type=text]{padding:8px 10px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--ink);width:100%}
.srcitem{display:flex;gap:8px;align-items:center;font-size:13px;padding:4px 0}
.srcitem .p{flex:1;word-break:break-all}
.srcitem .k{color:var(--muted);font-size:11px;border:1px solid var(--line);border-radius:5px;padding:1px 6px}
.pathval{flex:1;word-break:break-all;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:7px 9px;min-height:34px;font-size:13px;color:var(--ink)}
.pathval.empty{color:var(--muted)}
.row{display:flex;gap:8px;align-items:center}
.mini{border:1px solid var(--line);background:var(--card);color:var(--accent);border-radius:7px;padding:5px 10px;font-size:12px;cursor:pointer;white-space:nowrap}
.mini:hover{background:var(--accent);color:#fff}
.mini.danger{color:#c0392b;border-color:#c0392b}.mini.danger:hover{background:#c0392b;color:#fff}
.roots{display:flex;gap:6px;flex-wrap:wrap}
.crumbs{font-size:12px;color:var(--muted);word-break:break-all;margin:2px 0 6px}
.brow{display:flex;flex-direction:column;gap:2px;max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:8px;padding:6px;background:var(--bg)}
.brow .it{padding:6px 8px;border-radius:6px;cursor:pointer;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.brow .it:hover{background:color-mix(in srgb,var(--bg),var(--ink) 8%)}
.brow .it.dir{color:var(--accent);font-weight:600}
.primary{background:var(--accent);color:#fff;border:1px solid var(--accent);border-radius:8px;padding:8px 16px;font-size:14px;font-weight:600;cursor:pointer}
.primary:disabled{opacity:.55;cursor:default}
.ghost{background:var(--card);color:var(--muted);border:1px solid var(--line);border-radius:8px;padding:8px 16px;font-size:14px;cursor:pointer}
.hint{font-size:12px;color:var(--muted)}
.memo{color:var(--muted);font-size:13px}.due{white-space:nowrap}.meta{color:var(--muted);font-size:12px}
.empty{padding:40px;text-align:center;color:var(--muted)}
.tabs{display:flex;gap:6px;margin:12px 0 0;border-bottom:1px solid var(--line)}
.tab{background:transparent;border:1px solid transparent;border-bottom:none;color:var(--muted);border-radius:8px 8px 0 0;padding:8px 16px;font-size:14px;font-weight:600;cursor:pointer}
.tab[aria-pressed=true]{background:var(--card);border-color:var(--line);color:var(--ink)}
body:not(.served) .tabs{display:none}
.termcount{color:var(--muted);font-size:12.5px;margin-left:auto}
.termtext{white-space:normal;word-break:break-word}
footer{color:var(--muted);font-size:12px;margin-top:18px}
</style><style id="colhide"></style></head><body>
<script>window.__KT=__KTCFG__;</script>
<div class="wrap">
<style>
.ptabs{display:flex;flex-wrap:wrap;gap:2px;margin:2px 0 6px;border-bottom:2px solid var(--hairline);align-items:flex-end}
.ptab{appearance:none;border:1px solid var(--hairline);border-bottom:none;background:var(--surface);color:inherit;padding:5px 8px;border-radius:9px 9px 0 0;font-weight:700;font-size:13px;cursor:pointer;margin-bottom:-2px;max-width:280px;display:flex;align-items:center;gap:6px;text-align:left}
.ptab[aria-pressed="true"]{background:var(--accent,#2563eb);color:#fff;border-color:transparent}
.ptab .lbl{flex:1 1 auto;min-width:0;line-height:1.25;max-height:2.9em;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word}
.ptab .x{flex:0 0 auto;margin-left:2px;opacity:.7;font-weight:700;font-size:15px;line-height:1;cursor:pointer;border-radius:4px;padding:0 3px}
.ptab .x:hover{opacity:1;background:rgba(127,127,127,.25)}
.tepbar{display:flex;align-items:center;gap:10px;margin:2px 0 8px}
.tepbar .tephint{color:var(--muted);font-size:13px}
.tepframe{display:block;width:100%;height:calc(100vh - 84px);min-height:460px;border:1px solid var(--hairline);border-radius:8px;background:var(--surface)}
</style>
<div class="ptabs" id="ptabs"></div>
<div id="ptab-proj">
<h1>Kotonoha プロジェクト一覧 <span class="verbadge">__VER__</span><span class="srvbadge">サーバーモード（作成・実行が有効）</span></h1>
<div class="tabs" id="tabs" hidden>
  <button class="tab" id="tab-projects" data-view="projects" aria-pressed="true" type="button" title="プロジェクト一覧。定義行＝実行/出力/編集/詳細">プロジェクト</button>
  <button class="tab" id="tab-terms" data-view="terms" aria-pressed="false" type="button" title="用語集（全プロジェクト共通 _terms.tsv）の管理">用語管理</button>
  <button class="tab" id="tab-tm" data-view="tm" aria-pressed="false" type="button" title="TM（翻訳メモリ）エントリの一覧/検索/編集/削除">TM</button>
  <button class="tab" id="tab-history" data-view="history" aria-pressed="false" type="button" title="操作の履歴（日付・作業内容）。メモ追加・編集・削除可">履歴</button>
</div>
<div id="view-projects">
<div class="ctl">
  <button class="btn new" id="newbtn" type="button" title="新規プロジェクトを作成（名前・ソース・メイン/Product/サブTMを指定。作成して実行も可）">＋ 新規作成</button>
  <input id="q" type="search" placeholder="タイトル・メモ・ソースを検索…" title="タイトル・メモ・ソースを部分一致で絞り込み">
  <button class="chip" data-st="all" aria-pressed="true" title="すべての状態を表示">すべて</button>
  <button class="chip" data-st="作業中" aria-pressed="false" title="状態=作業中 のみ表示">作業中</button>
  <button class="chip" data-st="レビュー中" aria-pressed="false" title="状態=レビュー中 のみ表示">レビュー中</button>
  <button class="chip" data-st="完了" aria-pressed="false" title="状態=完了 のみ表示">完了</button>
  <label class="toggle" title="完了したプロジェクトを一覧から隠す"><input type="checkbox" id="hideDone"> 完了を隠す</label>
  <span class="colmenu" id="toolswrap" hidden><button class="btn" id="toolsbtn" type="button" title="MTを反映・索引キャッシュ作成・TM書き戻し・UI Glossary・ファイル比較・JAバージョンチェック">ツール ▾</button><div id="toolspanel" class="toolspanel" hidden></div></span>
  <span class="colmenu"><button class="btn" id="colbtn" type="button" title="表示する列の選択（ブラウザに保存）">列 ▾</button><div id="colpanel" hidden></div></span>
  <button class="btn" id="resetbtn" type="button" title="列幅・表示・並び順を既定に戻す">既定に戻す</button>
  <button class="btn" id="lockbtn" type="button" aria-pressed="false" title="列の並べ替え/幅変更をロック">固定</button>
  <button class="themebtn" id="theme" title="ライト/ダークのテーマ切替">◐ テーマ</button>
</div>
<div id="newnote" class="note" hidden>新規プロジェクトの作成・実行はランチャー <b>TM-Match-Explorer.bat</b> で行います：メニュー <b>[C]</b> プロジェクト作成＋実行（単一記事・フォルダーいずれも／メイン＋Product＋サブ TM）、または <b>[P]</b> 画面の <b>N=新規作成</b>・<b>G=保存した定義を実行</b>。作成・実行後にこのページを再読み込み（F5）すると一覧へ反映されます。<button class="btn" id="newclose" type="button" style="margin-left:8px">閉じる</button></div>
<div class="tablewrap"><table id="ptable"><colgroup id="cg"></colgroup>
<thead><tr id="thr"></tr></thead><tbody id="rows"></tbody></table></div>
<div class="empty" id="empty" hidden>該当するプロジェクトはありません。</div>
</div><!-- /view-projects -->
<div id="view-terms" hidden>
  <div class="ctl">
    <button class="btn new" id="termadd" type="button" title="用語を新規追加（ソースEN・ターゲットJA・用例・ノート）">＋ 用語を追加</button>
    <input id="tq" type="search" placeholder="用語を検索（ソース・ターゲット・ノート・ドキュメント）…" title="用語集をソース/ターゲット/ノート/ドキュメントで絞り込み">
    <button class="btn" id="termextract" type="button" title="ソース/TEP/XLIFF から UI 用語を抽出して登録">用語を抽出…</button>
    <span class="colmenu"><button class="btn" id="termexportbtn" type="button" title="用語集を TSV/CSV/XLSX で書き出し">エクスポート ▾</button><div id="termexportpanel" class="toolspanel" hidden></div></span>
    <span class="termcount" id="termcount" title="登録用語数"></span>
  </div>
  <div class="tablewrap"><table id="ttable"><colgroup>
    <col style="width:200px"><col style="width:200px"><col style="width:260px"><col style="width:160px"><col style="width:150px"><col style="width:120px"><col style="width:128px"><col style="width:120px"></colgroup>
  <thead><tr><th>ソース</th><th>ターゲット</th><th>用例</th><th>ノート</th><th>ドキュメント</th><th>プロジェクト</th><th>更新</th><th class="act">操作</th></tr></thead>
  <tbody id="trows"></tbody></table></div>
  <div class="empty" id="tempty" hidden>用語がありません。「＋ 用語を追加」または「用語を抽出…」で登録してください。</div>
</div><!-- /view-terms -->
<div id="view-tm" hidden>
  <div class="ctl">
    <select id="tmsel" title="編集する TM を選択（XTML は読み取り専用）"></select>
    <input id="tmq" type="search" placeholder="TMを検索（EN・JA 部分一致）…" title="EN/JA を部分一致で絞り込み">
    <button class="btn new" id="tmaddbtn" type="button" title="選択中の TM にエントリ（EN/JA）を追加">＋ エントリ追加</button>
    <span class="termcount" id="tmcount" title="表示中のエントリ数"></span>
    <span class="termcount" id="tminfo" style="opacity:.75" title="選択中TMの編集可否"></span>
  </div>
  <div class="tablewrap"><table id="tmtable"><colgroup>
    <col style="width:44%"><col style="width:44%"><col style="width:132px"><col style="width:120px"></colgroup>
  <thead><tr><th>EN（原文）</th><th>JA（訳）</th><th>更新</th><th class="act">操作</th></tr></thead>
  <tbody id="tmrows"></tbody></table></div>
  <div class="empty" id="tmempty" hidden>エントリがありません（または検索に一致しません）。編集可能なTM（書込可能・XTM以外）を選択してください。</div>
</div><!-- /view-tm -->
<div id="view-history" hidden>
  <div class="ctl">
    <input id="hq" type="search" placeholder="履歴を検索（作業内容・メモ・プロジェクト）…" title="作業内容・メモ・プロジェクト名で絞り込み">
    <span class="termcount" id="hcount" title="履歴件数"></span>
    <button class="btn" id="hrefresh" type="button" title="履歴を再読み込み">更新</button>
  </div>
  <div class="tablewrap"><table id="htable"><colgroup>
    <col style="width:150px"><col style="width:120px"><col style="width:34%"><col style="width:34%"><col style="width:110px"></colgroup>
  <thead><tr><th>日付</th><th>種別</th><th>作業内容</th><th>メモ</th><th class="act">操作</th></tr></thead>
  <tbody id="hrows"></tbody></table></div>
  <div class="empty" id="hempty" hidden>履歴はまだありません。作成・実行・出力などの操作を行うと自動で記録されます。</div>
</div><!-- /view-history -->
</div><!-- /ptab-proj -->
<div id="tepviews"></div>
<footer>台帳: _projects.json ／ 用語集: _terms.tsv（全プロジェクト共通）／ この一覧は <code>projects.py dashboard</code> で生成。開き直すと最新になります。</footer>
</div>
<script>
let P = __DATA__;
const COLS = __COLS__;
const KT = (window.__KT||{served:false,token:""});
const BADGE={"未解析":"b-todo","作業中":"b-work","レビュー中":"b-rev","完了":"b-done"};
const esc=s=>String(s==null?"":s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
const LSW="kotonoha-proj-w",LSH="kotonoha-proj-hidden",LST="kotonoha-proj-theme";
let widths={},hidden=[];
try{widths=JSON.parse(localStorage.getItem(LSW)||"{}")||{}}catch(e){}
try{hidden=JSON.parse(localStorage.getItem(LSH)||"[]")||[]}catch(e){}
try{const t=localStorage.getItem(LST);if(t)document.documentElement.setAttribute("data-theme",t);}catch(e){}
const state={q:"",st:"all",hideDone:false};
const cg=document.getElementById("cg"),thr=document.getElementById("thr"),styleHide=document.getElementById("colhide");
const LSO="kotonoha-proj-order",LSLK="kotonoha-proj-lock";
const DEFAULTS=COLS.map(c=>({...c}));
let locked=false;try{locked=localStorage.getItem(LSLK)==="1"}catch(e){}
try{const ord=JSON.parse(localStorage.getItem(LSO)||"[]");if(ord&&ord.length){COLS.sort((a,b)=>{let i=ord.indexOf(a.id),j=ord.indexOf(b.id);if(i<0)i=99;if(j<0)j=99;return i-j;});}}catch(e){}
function colEls(){return cg.querySelectorAll("col");}
let drag=null,dnd=null;

// build colgroup + header (resize handle + drag-to-reorder) + fixed action column
function buildHead(){
  cg.innerHTML="";thr.innerHTML="";
  COLS.forEach((c,i)=>{
    const col=document.createElement("col");col.style.width=((widths[c.id]||c.w))+"px";cg.appendChild(col);
    const th=document.createElement("th");th.textContent=c.label;th.draggable=!locked;th.title=locked?"固定中（解除は固定ボタン）":"ドラッグで並べ替え／右端で幅調整";
    const rz=document.createElement("span");rz.className="rz";rz.draggable=false;th.appendChild(rz);
    rz.addEventListener("mousedown",e=>{e.stopPropagation();th.draggable=false;startDrag(e,i);});
    th.addEventListener("dragstart",()=>{dnd=i;});
    th.addEventListener("dragover",e=>{e.preventDefault();th.classList.add("dragover");});
    th.addEventListener("dragleave",()=>th.classList.remove("dragover"));
    th.addEventListener("drop",e=>{e.preventDefault();th.classList.remove("dragover");if(dnd!=null&&dnd!==i){reorder(dnd,i);}dnd=null;});
    th.addEventListener("dragend",()=>{dnd=null;thr.querySelectorAll("th").forEach(x=>x.classList.remove("dragover"));});
    thr.appendChild(th);
  });
  const acol=document.createElement("col");acol.style.width=(KT.served?"240px":"88px");cg.appendChild(acol);
  const ath=document.createElement("th");ath.className="act";ath.textContent="操作";ath.draggable=false;thr.appendChild(ath);
  document.getElementById("ptable").classList.toggle("locked",locked);
}
function reorder(from,to){const m=COLS.splice(from,1)[0];COLS.splice(to,0,m);try{localStorage.setItem(LSO,JSON.stringify(COLS.map(c=>c.id)))}catch(e){}buildHead();buildMenu();applyHidden();render();}
function startDrag(e,i){e.preventDefault();drag={i,x:e.clientX,w:colEls()[i].getBoundingClientRect().width};document.body.style.cursor="col-resize";}
document.addEventListener("mousemove",e=>{if(!drag)return;const w=Math.max(36,Math.round(drag.w+(e.clientX-drag.x)));colEls()[drag.i].style.width=w+"px";});
document.addEventListener("mouseup",()=>{if(drag){const c=COLS[drag.i];widths[c.id]=parseInt(colEls()[drag.i].style.width,10);try{localStorage.setItem(LSW,JSON.stringify(widths))}catch(e){}drag=null;document.body.style.cursor="";}if(!locked){thr.querySelectorAll("th").forEach(t=>{if(!t.classList.contains("act"))t.draggable=true;});}});

// column show/hide
function applyHidden(){
  styleHide.textContent=hidden.map(id=>{const i=COLS.findIndex(c=>c.id===id);return i<0?"":("#ptable th:nth-child("+(i+1)+"),#ptable td:nth-child("+(i+1)+"){display:none}");}).join("\n");
  try{localStorage.setItem(LSH,JSON.stringify(hidden))}catch(e){}
}
const panel=document.getElementById("colpanel");
function buildMenu(){
  panel.innerHTML="";
  COLS.forEach(c=>{
    const lab=document.createElement("label");
    lab.innerHTML='<input type="checkbox" '+(hidden.includes(c.id)?"":"checked")+'> '+esc(c.label);
    panel.appendChild(lab);
    lab.querySelector("input").addEventListener("change",e=>{if(e.target.checked){hidden=hidden.filter(x=>x!==c.id);}else if(!hidden.includes(c.id)){hidden.push(c.id);}applyHidden();});
  });
}
document.getElementById("colbtn").addEventListener("click",()=>{panel.hidden=!panel.hidden;});
document.addEventListener("click",e=>{if(!e.target.closest(".colmenu"))panel.hidden=true;});

// rows (open は列ではなく右端固定の独立ボタン)
function cell(p,id){
  if(id==="n")return '<td class="n">'+p.n+'</td>';
  if(id==="title")return '<td class="ti">'+esc(p.title)+'<div class="meta">'+esc(p.source||"")+'</div></td>';
  if(id==="status")return '<td><span class="badge '+(BADGE[p.status]||"")+'">'+esc(p.status)+'</span></td>';
  if(id==="segmt")return '<td class="n">'+(p.segs==null?"–":p.segs)+' / '+(p.mt==null?"–":p.mt)+'</td>';
  if(id==="due")return '<td class="due">'+esc(p.due||"–")+'</td>';
  if(id==="memo")return '<td class="memo">'+esc(p.memo||"")+'</td>';
  if(id==="updated")return '<td class="meta">'+esc(p.updated||"")+'</td>';
  return "<td></td>";
}
function render(){
  const q=state.q.trim().toLowerCase();
  const list=P.filter(p=>{
    if(state.st!=="all"&&p.status!==state.st)return false;
    if(state.hideDone&&p.status==="完了")return false;
    if(q){const hay=(p.title+" "+(p.memo||"")+" "+(p.source||"")).toLowerCase();if(!hay.includes(q))return false;}
    return true;
  });
  document.getElementById("empty").hidden=list.length>0;
  document.getElementById("rows").innerHTML=list.map(p=>{
    let inner="";
    if(p.pid){inner='<button class="run" type="button" data-pid="'+esc(p.pid)+'" data-cmd="'+esc(p.cmd)+'" data-n="'+p.n+'" title="'+(KT.served?'クリックで解析＋Pre-translation を実行（結果はプロジェクト名タブに表示）':'クリックで実行コマンドをコピー ／ またはランチャー [P] で G → 番号 '+p.n)+'">実行</button>';
      if(KT.served){inner+='<button class="exp" type="button" data-pid="'+esc(p.pid)+'" title="TM を適用して元の形式で翻訳版を出力（.json/.docx/.xlsx 等。TEP確定→TM書き戻しの後に実行）">出力</button>';}}
    else if(p.uri){inner='<a class="open" href="'+esc(p.uri)+'" data-title="'+esc(p.project||p.title||p.name||"")+'" target="_blank" rel="noopener">開く</a>';}
    if(KT.served&&p.id){inner+='<button class="edit" type="button" data-id="'+esc(p.id)+'" title="状態・メモ・期日・削除">編集</button>';}
    if(KT.served&&p.pid){inner+='<button class="det" type="button" data-pid="'+esc(p.pid)+'" aria-pressed="false" title="作業サマリーと中間生成物（_Details フォルダー）を表示">詳細</button>';}
    var main="<tr>"+COLS.map(c=>cell(p,c.id)).join("")+'<td class="act">'+inner+'</td></tr>';
    if(KT.served&&p.pid){main+='<tr class="detrow" id="detrow-'+esc(p.pid)+'" hidden><td colspan="'+(COLS.length+1)+'"><div class="detpanel" id="detpanel-'+esc(p.pid)+'"></div></td></tr>';}
    return main;
  }).join("");
}
// clipboard copy (file:// では navigator.clipboard が無い場合があるので execCommand に退避)
function fallbackCopy(t){try{const ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.focus();ta.select();const ok=document.execCommand("copy");document.body.removeChild(ta);return ok;}catch(e){return false;}}
function copyText(t){return (navigator.clipboard&&navigator.clipboard.writeText)?navigator.clipboard.writeText(t).then(()=>true,()=>fallbackCopy(t)):Promise.resolve(fallbackCopy(t));}
let toastT=null;
function toast(msg){let el=document.getElementById("toast");if(!el){el=document.createElement("div");el.id="toast";document.body.appendChild(el);}el.textContent=msg;el.classList.add("show");clearTimeout(toastT);toastT=setTimeout(()=>el.classList.remove("show"),3000);}
document.getElementById("rows").addEventListener("click",e=>{
  const tep=e.target.closest("a.tep[data-path]");
  if(tep&&KT.served){e.preventDefault();openTEPbyPath(tep.getAttribute("data-path"),tep.textContent.replace(/（.*/,"").trim());return;}
  const rv=e.target.closest("[data-reveal]");
  if(rv&&KT.served){e.preventDefault();api("/api/open",{method:"POST",body:JSON.stringify({path:rv.getAttribute("data-reveal")})}).then(r=>toast(r&&r.ok?"保存場所を開きました":("開けませんでした："+((r&&r.error)||""))));return;}
  const dopen=e.target.closest("button.detopen");
  if(dopen&&KT.served){api("/api/open",{method:"POST",body:JSON.stringify({path:dopen.getAttribute("data-path")})}).then(r=>toast(r&&r.ok?"フォルダーを開きました":("開けませんでした："+((r&&r.error)||""))));return;}
  const eb=e.target.closest("button.edit");
  if(eb&&KT.served){const id=eb.getAttribute("data-id");const row=P.find(x=>x.id===id);if(row)openEdit(row);return;}
  const db=e.target.closest("button.det");
  if(db&&KT.served){toggleDetails(db.getAttribute("data-pid"),db);return;}
  const xb=e.target.closest("button.exp");
  if(xb&&KT.served){openExportChoice(xb.getAttribute("data-pid"),xb);return;}
  const b=e.target.closest("button.run");if(!b)return;
  const pid=b.getAttribute("data-pid"),cmd=b.getAttribute("data-cmd"),n=b.getAttribute("data-n");
  if(KT.served&&pid){
    b.disabled=true;const old=b.textContent;b.textContent="実行中…";
    api("/api/run",{method:"POST",body:JSON.stringify({id:pid})}).then(r=>{
      b.disabled=false;b.textContent=old;
      toast(r&&r.ok?("実行完了（生成 "+(r.registered||0)+" 件）"):("実行失敗："+((r&&r.error)||"不明なエラー")));
      refresh().then(function(){if(r&&r.ok&&r.produced)openProduced(r.project,r.produced);});
    }).catch(err=>{b.disabled=false;b.textContent=old;toast("通信エラー: "+err);});
    return;
  }
  copyText(cmd).then(ok=>toast(ok?("実行コマンドをコピーしました。ターミナルに貼り付けて実行 ／ またはランチャー [P] → G → 番号 "+n):("コピーできませんでした。手動でコピーしてください: "+cmd)));
});
document.getElementById("q").addEventListener("input",e=>{state.q=e.target.value;render();});
document.getElementById("hideDone").addEventListener("change",e=>{state.hideDone=e.target.checked;render();});
document.querySelectorAll(".chip").forEach(b=>b.addEventListener("click",()=>{
  state.st=b.dataset.st;document.querySelectorAll(".chip").forEach(x=>x.setAttribute("aria-pressed",x===b));render();
}));
document.getElementById("theme").addEventListener("click",()=>{
  const cur=document.documentElement.getAttribute("data-theme");
  const dark=cur?cur==="dark":matchMedia("(prefers-color-scheme:dark)").matches;
  const nv=dark?"light":"dark";document.documentElement.setAttribute("data-theme",nv);
  try{localStorage.setItem(LST,nv)}catch(e){}
});
document.getElementById("newbtn").addEventListener("click",()=>{if(KT.served){openCreate();return;}const n=document.getElementById("newnote");n.hidden=!n.hidden;});
document.getElementById("newclose").addEventListener("click",()=>{document.getElementById("newnote").hidden=true;});
document.getElementById("resetbtn").addEventListener("click",()=>{
  COLS.splice(0,COLS.length,...DEFAULTS.map(c=>({...c})));widths={};hidden=[];
  try{localStorage.removeItem(LSO);localStorage.removeItem(LSW);localStorage.removeItem(LSH);}catch(e){}
  buildHead();buildMenu();applyHidden();render();
});
function updateLockBtn(){const b=document.getElementById("lockbtn");b.setAttribute("aria-pressed",String(locked));b.textContent=locked?"固定中":"固定";}
document.getElementById("lockbtn").addEventListener("click",()=>{
  locked=!locked;try{localStorage.setItem(LSLK,locked?"1":"0")}catch(e){}
  updateLockBtn();buildHead();render();
});
updateLockBtn();
buildHead();buildMenu();applyHidden();render();

// ===== サーバーモード (projects.py serve): ブラウザから作成・実行 =====
function api(path,opts){opts=opts||{};opts.headers=Object.assign({"X-KT-Token":KT.token,"Content-Type":"application/json"},opts.headers||{});return fetch(path,opts).then(r=>r.json());}
function refresh(){return api("/api/projects").then(d=>{if(d&&d.rows){P=d.rows;render();}}).catch(()=>{});}
// Windows ネイティブのファイル/フォルダー選択（サーバー側 tkinter）。使えない時は false。
function pick(kind,multiple){return api("/api/pick",{method:"POST",body:JSON.stringify({kind:kind,multiple:!!multiple})});}
function el(tag,cls,txt){const e=document.createElement(tag);if(cls)e.className=cls;if(txt!=null)e.textContent=txt;return e;}
function closeOvl(){const o=document.getElementById("ovl");if(o)o.remove();}
function overlay(node){closeOvl();const o=el("div");o.id="ovl";o.className="ovl";o.appendChild(node);o.addEventListener("mousedown",e=>{if(e.target===o)closeOvl();});document.body.appendChild(o);return o;}
// kind: 'tmx' | 'source' | 'dir'
function openBrowser(kind,startDir,onPick){
  const m=el("div","modal");
  m.appendChild(el("h2",null,kind==="dir"?"フォルダーを選択":(kind==="tmx"?"TM (.tmx) を選択":"ソース (.mdx / .md) を選択")));
  const bd=el("div","bd");const roots=el("div","roots");const crumbs=el("div","crumbs");const listw=el("div","brow");
  bd.appendChild(roots);bd.appendChild(crumbs);bd.appendChild(listw);m.appendChild(bd);
  const ft=el("div","ft");let curDir=startDir||"";
  if(kind==="dir"){const pick=el("button","primary","このフォルダーを選択");pick.onclick=()=>{if(curDir){onPick(curDir);closeOvl();}};ft.appendChild(pick);}
  const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;ft.appendChild(cancel);m.appendChild(ft);
  function load(dir){
    api("/api/browse?kind="+encodeURIComponent(kind)+"&dir="+encodeURIComponent(dir||"")).then(d=>{
      if(d.error){toast("参照エラー: "+d.error);return;}
      curDir=d.dir;crumbs.textContent=d.dir||"";
      roots.innerHTML="";(d.roots||[]).forEach(r=>{const b=el("button","mini",r.name);b.title=r.path;b.onclick=()=>load(r.path);roots.appendChild(b);});
      listw.innerHTML="";
      if(d.parent){const up=el("div","it dir","↑ 上の階層");up.onclick=()=>load(d.parent);listw.appendChild(up);}
      (d.dirs||[]).forEach(x=>{const it=el("div","it dir","▸ "+x.name);it.onclick=()=>load(x.path);listw.appendChild(it);});
      if(kind!=="dir")(d.files||[]).forEach(x=>{const it=el("div","it","・ "+x.name);it.onclick=()=>{onPick(x.path);closeOvl();};listw.appendChild(it);});
      if(!(d.dirs||[]).length && (kind==="dir" || !(d.files||[]).length)){listw.appendChild(el("div","hint",kind==="dir"?"（サブフォルダーなし。上の『このフォルダーを選択』で確定）":"（該当ファイルなし）"));}
    }).catch(err=>toast("通信エラー: "+err));
  }
  overlay(m);load(startDir||"");
}
function openCreate(){
  let runmtDefault=true;try{runmtDefault=(localStorage.getItem("kotonoha-proj-runmt")!=="0");}catch(e){}
  const st={name:"",sources:[],main_tm:"",product_tm:"",sub_tms:[],run_mt:runmtDefault};
  const m=el("div","modal");m.appendChild(el("h2",null,"新規プロジェクトの作成"));
  const bd=el("div","bd");
  bd.appendChild(el("div","hint","ソース・TM は Windows の「ファイルを開く」ダイアログで選択します（ダイアログが前面に出ます）。"));
  // 名前
  const fn=el("div","fld");fn.appendChild(el("label",null,"プロジェクト名"));
  const nameI=el("input");nameI.type="text";nameI.placeholder="例: Spring Release 2026";nameI.oninput=()=>{st.name=nameI.value;};fn.appendChild(nameI);bd.appendChild(fn);
  // ソース
  const fs=el("div","fld");fs.appendChild(el("label",null,"ソース（.mdx / .md ファイル、またはフォルダー・複数可）"));
  const srcList=el("div");fs.appendChild(srcList);
  const sb=el("div","roots");const addF=el("button","mini","＋ ファイル追加");const addD=el("button","mini","＋ フォルダー追加");sb.appendChild(addF);sb.appendChild(addD);fs.appendChild(sb);bd.appendChild(fs);
  function drawSrc(){srcList.innerHTML="";if(!st.sources.length){srcList.appendChild(el("div","hint","（未追加）"));}
    st.sources.forEach((s,i)=>{const r=el("div","srcitem");r.appendChild(el("span","k",s.kind==="dir"?"フォルダー":"ファイル"));const pp=el("span","p",s.path);r.appendChild(pp);const x=el("button","mini danger","削除");x.onclick=()=>{st.sources.splice(i,1);drawSrc();};r.appendChild(x);srcList.appendChild(r);});}
  addF.onclick=()=>pick("source",true).then(r=>{if(r&&r.available===false){openBrowser("source","",p=>{st.sources.push({kind:"file",path:p});drawSrc();});return;}(r&&r.paths||[]).forEach(p=>st.sources.push({kind:"file",path:p}));drawSrc();}).catch(err=>toast("選択エラー: "+err));
  addD.onclick=()=>pick("dir",false).then(r=>{if(r&&r.available===false){openBrowser("dir","",p=>{st.sources.push({kind:"dir",path:p});drawSrc();});return;}(r&&r.paths||[]).forEach(p=>st.sources.push({kind:"dir",path:p}));drawSrc();}).catch(err=>toast("選択エラー: "+err));
  drawSrc();
  // メイン TM / Product TM
  function pathField(label,hint,get,set){const f=el("div","fld");f.appendChild(el("label",null,label));if(hint)f.appendChild(el("div","hint",hint));const row=el("div","row");const v=el("div","pathval");const choose=el("button","mini","選択");const clr=el("button","mini danger","クリア");row.appendChild(v);row.appendChild(choose);row.appendChild(clr);f.appendChild(row);
    function draw(){const val=get();v.textContent=val||"（未選択）";v.classList.toggle("empty",!val);}
    choose.onclick=()=>pick("tmx",false).then(r=>{if(r&&r.available===false){openBrowser("tmx","",p=>{set(p);draw();});return;}if((r&&r.paths||[]).length){set(r.paths[0]);draw();}}).catch(err=>toast("選択エラー: "+err));
    clr.onclick=()=>{set("");draw();};draw();return f;}
  function newTmxField(label,hint,get,set){const f=el("div","fld");f.appendChild(el("label",null,label));if(hint)f.appendChild(el("div","hint",hint));const row=el("div","row");const v=el("div","pathval");const choose=el("button","mini","選択");const mk=el("button","mini","＋ 新規作成");const clr=el("button","mini danger","クリア");row.appendChild(v);row.appendChild(choose);row.appendChild(mk);row.appendChild(clr);f.appendChild(row);
    function draw(){const val=get();v.textContent=val||"（未選択）";v.classList.toggle("empty",!val);}
    choose.onclick=()=>pick("tmx",false).then(r=>{if(r&&r.available===false){openBrowser("tmx","",p=>{set(p);draw();});return;}if((r&&r.paths||[]).length){set(r.paths[0]);draw();}}).catch(err=>toast("選択エラー: "+err));
    mk.onclick=()=>{mk.disabled=true;api("/api/new-tmx",{method:"POST",body:JSON.stringify({})}).then(r=>{mk.disabled=false;if(!r||r.available===false){toast("新規作成はサーバーモードでのみ利用できます");return;}if(r.ok&&r.path){set(r.path);draw();toast("空のメイン TM を作成しました");}else if(!r.path){/*キャンセル*/}else{toast("作成失敗："+(r.error||"不明"));}}).catch(err=>{mk.disabled=false;toast("通信エラー: "+err);});};
    clr.onclick=()=>{set("");draw();};draw();return f;}
  bd.appendChild(newTmxField("メイン TM（.tmx・1つ・必須／マッチ用）","既存の .tmx を選択、または「＋ 新規作成」で空の TM を作成できます。",()=>st.main_tm,x=>{st.main_tm=x;}));
  bd.appendChild(pathField("Product TM（.tmx・任意／用語集ヒント）","UI 用語の一致＋AI 翻訳の用語集ヒントに使います。",()=>st.product_tm,x=>{st.product_tm=x;}));
  // サブ TM（複数）
  const fsub=el("div","fld");fsub.appendChild(el("label",null,"サブ TM（.tmx・任意・複数可／マッチ用）"));const subList=el("div");fsub.appendChild(subList);const addSub=el("button","mini","＋ サブ TM 追加");fsub.appendChild(addSub);bd.appendChild(fsub);
  function drawSub(){subList.innerHTML="";if(!st.sub_tms.length){subList.appendChild(el("div","hint","（未追加）"));}st.sub_tms.forEach((t,i)=>{const r=el("div","srcitem");r.appendChild(el("span","p",t));const x=el("button","mini danger","削除");x.onclick=()=>{st.sub_tms.splice(i,1);drawSub();};r.appendChild(x);subList.appendChild(r);});}
  addSub.onclick=()=>pick("tmx",true).then(r=>{if(r&&r.available===false){openBrowser("tmx","",p=>{st.sub_tms.push(p);drawSub();});return;}(r&&r.paths||[]).forEach(p=>st.sub_tms.push(p));drawSub();}).catch(err=>toast("選択エラー: "+err));drawSub();
  // MTを実行（既訳のない≤74%セグメントのMTを翻訳欄に反映する／OFFなら翻訳欄は英語のまま・MTは履歴ペインに表示）
  const fmt=el("div","fld");
  const mtlab=el("label","toggle2");const mtcb=el("input");mtcb.type="checkbox";mtcb.checked=!!st.run_mt;
  mtlab.appendChild(mtcb);mtlab.appendChild(document.createTextNode(" MTを実行（既訳のないセグメントのMTを翻訳欄に反映）"));
  fmt.appendChild(mtlab);
  fmt.appendChild(el("div","hint","OFF にすると翻訳欄は英語のまま表示し、MT の結果は翻訳履歴ペインに「MT」として表示します（作業ファイルで後から「MTを実行する」ボタンでも反映できます）。この選択は次回の作成時にも引き継がれます。"));
  mtcb.onchange=()=>{st.run_mt=mtcb.checked;try{localStorage.setItem("kotonoha-proj-runmt",mtcb.checked?"1":"0");}catch(e){}};
  bd.appendChild(fmt);
  m.appendChild(bd);
  // フッター
  const ft=el("div","ft");const run=el("button","primary","作成して実行");const mk=el("button","primary","保存");const cancel=el("button","ghost","キャンセル");
  ft.appendChild(run);ft.appendChild(mk);ft.appendChild(cancel);m.appendChild(ft);cancel.onclick=closeOvl;
  function validate(){if(!st.name.trim()){toast("プロジェクト名を入力してください");return false;}if(!st.sources.length){toast("ソースを1つ以上追加してください");return false;}if(!st.main_tm){toast("メイン TM を選択してください");return false;}return true;}
  function create(then){if(!validate())return;run.disabled=true;mk.disabled=true;
    api("/api/create",{method:"POST",body:JSON.stringify(st)}).then(r=>{
      if(!r||!r.id){run.disabled=false;mk.disabled=false;toast("作成失敗："+((r&&r.error)||"不明"));return;}
      if(then==="run"){toast("作成しました。実行中…");api("/api/run",{method:"POST",body:JSON.stringify({id:r.id})}).then(rr=>{closeOvl();toast(rr&&rr.ok?("実行完了（生成 "+(rr.registered||0)+" 件）"):("作成済／実行失敗："+((rr&&rr.error)||"不明")));refresh().then(function(){if(rr&&rr.ok&&rr.produced)openProduced(rr.project,rr.produced);});}).catch(err=>{closeOvl();toast("作成済／実行の通信エラー: "+err);refresh();});}
      else{closeOvl();toast("プロジェクトを作成しました（定義として保存）");refresh();}
    }).catch(err=>{run.disabled=false;mk.disabled=false;toast("通信エラー: "+err);});}
  run.onclick=()=>create("run");mk.onclick=()=>create("mk");
  overlay(m);nameI.focus();
}

// ===== 全機能GUI化: 行の編集／ツールメニューのダイアログ群 =====
function modalShell(title){const m=el("div","modal");m.appendChild(el("h2",null,title));const bd=el("div","bd");m.appendChild(bd);const ft=el("div","ft");return {m:m,bd:bd,ft:ft};}
function textField(label,hint,val,set,ph){const f=el("div","fld");f.appendChild(el("label",null,label));if(hint)f.appendChild(el("div","hint",hint));const i=el("input");i.type="text";if(ph)i.placeholder=ph;if(val!=null)i.value=val;i.oninput=()=>set(i.value);f.appendChild(i);return f;}
function pathFieldK(label,hint,kind,get,set){const f=el("div","fld");f.appendChild(el("label",null,label));if(hint)f.appendChild(el("div","hint",hint));const row=el("div","row");const v=el("div","pathval");const choose=el("button","mini","選択");const clr=el("button","mini danger","クリア");row.appendChild(v);row.appendChild(choose);row.appendChild(clr);f.appendChild(row);
  function draw(){const val=get();v.textContent=val||"（未選択）";v.classList.toggle("empty",!val);}
  choose.onclick=()=>pick(kind,false).then(r=>{if(r&&r.available===false){openBrowser(kind,"",p=>{set(p);draw();});return;}if((r&&r.paths||[]).length){set(r.paths[0]);draw();}}).catch(err=>toast("選択エラー: "+err));
  clr.onclick=()=>{set("");draw();};draw();return f;}
function listFieldK(label,hint,kind,arr){const f=el("div","fld");f.appendChild(el("label",null,label));if(hint)f.appendChild(el("div","hint",hint));const listw=el("div");f.appendChild(listw);const add=el("button","mini","＋ 追加");f.appendChild(add);
  function draw(){listw.innerHTML="";if(!arr.length){listw.appendChild(el("div","hint","（未追加）"));}arr.forEach((p,i)=>{const r=el("div","srcitem");r.appendChild(el("span","p",p));const x=el("button","mini danger","削除");x.onclick=()=>{arr.splice(i,1);draw();};r.appendChild(x);listw.appendChild(r);});}
  add.onclick=()=>pick(kind,true).then(r=>{if(r&&r.available===false){openBrowser(kind,"",p=>{arr.push(p);draw();});return;}(r&&r.paths||[]).forEach(p=>arr.push(p));draw();}).catch(err=>toast("選択エラー: "+err));
  draw();return f;}
function busy(btn,on,label){if(on){btn.dataset.old=btn.textContent;btn.textContent=label||"実行中…";btn.disabled=true;}else{btn.textContent=btn.dataset.old||btn.textContent;btn.disabled=false;}}
function showLog(title,log,revealPath){const sh=modalShell(title);const pre=el("div","pre");pre.textContent=log||"(出力なし)";sh.bd.appendChild(pre);const close=el("button","primary","閉じる");close.onclick=closeOvl;if(revealPath){const open=el("button","ghost","出力フォルダを開く");open.onclick=()=>api("/api/reveal",{method:"POST",body:JSON.stringify({path:revealPath})}).then(r=>{if(!(r&&r.ok))toast("フォルダを開けませんでした");});sh.ft.appendChild(open);}sh.ft.appendChild(close);sh.m.appendChild(sh.ft);overlay(sh.m);}

function openEdit(p){
  const st={status:p.status||"未解析",memo:p.memo||"",due:p.due||""};
  const sh=modalShell("編集: "+(p.title||p.id||""));
  const fs=el("div","fld");fs.appendChild(el("label",null,"状態"));const sel=el("select");["未解析","作業中","レビュー中","完了"].forEach(s=>{const o=el("option",null,s);o.value=s;if(s===st.status)o.selected=true;sel.appendChild(o);});sel.onchange=()=>{st.status=sel.value;};fs.appendChild(sel);sh.bd.appendChild(fs);
  sh.bd.appendChild(textField("メモ","",st.memo,v=>{st.memo=v;}));
  sh.bd.appendChild(textField("期日 (YYYY-MM-DD)","",st.due,v=>{st.due=v;},"2026-12-31"));
  const del=el("button","ghost","このプロジェクトを削除");del.style.color="#c0392b";let armed=false;
  del.onclick=()=>{if(!armed){armed=true;del.textContent="本当に削除？（もう一度クリックで確定）";return;}busy(del,true,"削除中…");api("/api/remove",{method:"POST",body:JSON.stringify({id:p.id,delete_file:false})}).then(r=>{closeOvl();toast(r&&r.ok?"削除しました":("削除失敗："+((r&&r.error)||"不明")));refresh();}).catch(err=>{busy(del,false);toast("通信エラー: "+err);});};
  const save=el("button","primary","保存");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  save.onclick=()=>{busy(save,true,"保存中…");Promise.all([
      api("/api/set-status",{method:"POST",body:JSON.stringify({id:p.id,status:st.status})}),
      api("/api/set-memo",{method:"POST",body:JSON.stringify({id:p.id,memo:st.memo})}),
      api("/api/set-due",{method:"POST",body:JSON.stringify({id:p.id,due:st.due})})
    ]).then(()=>{closeOvl();toast("更新しました");refresh();}).catch(err=>{busy(save,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(del);sh.ft.appendChild(cancel);sh.ft.appendChild(save);sh.m.appendChild(sh.ft);overlay(sh.m);
}

function openInject(){
  const st={mode:"single",html:"",mt:"",combined_todo:"",combined_mt:""};
  const sh=modalShell("MTをHTMLに反映");
  sh.bd.appendChild(el("div","hint","翻訳済み mt-done は Claude 等で作成した成果物を指定します。単一＝1記事HTML＋mt-done、一括＝combined.mt-todo.json＋combined.mt-done.jsonl。"));
  const fm=el("div","fld");fm.appendChild(el("label",null,"モード"));const sel=el("select");[["single","単一（HTML＋mt-done）"],["batch","一括（combined）"]].forEach(o=>{const op=el("option",null,o[1]);op.value=o[0];sel.appendChild(op);});fm.appendChild(sel);sh.bd.appendChild(fm);
  const single=el("div");const batch=el("div");batch.hidden=true;
  single.appendChild(pathFieldK("HTML（生成済み）","",'html',()=>st.html,x=>{st.html=x;}));
  single.appendChild(pathFieldK("mt-done（.jsonl / .json）","",'json',()=>st.mt,x=>{st.mt=x;}));
  batch.appendChild(pathFieldK("combined.mt-todo.json","",'json',()=>st.combined_todo,x=>{st.combined_todo=x;}));
  batch.appendChild(pathFieldK("combined.mt-done.jsonl","",'json',()=>st.combined_mt,x=>{st.combined_mt=x;}));
  sh.bd.appendChild(single);sh.bd.appendChild(batch);
  sel.onchange=()=>{st.mode=sel.value;single.hidden=(st.mode!=="single");batch.hidden=(st.mode!=="batch");};
  const run=el("button","primary","反映");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  run.onclick=()=>{busy(run,true,"反映中…");api("/api/inject",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(run,false);if(r&&r.ok){toast("反映しました");showLog("MT反映結果",r.log);}else{toast("反映失敗："+((r&&r.error)||"不明"));if(r&&r.log)showLog("MT反映ログ",r.log);}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(run);sh.m.appendChild(sh.ft);overlay(sh.m);
}

function openPrebuild(){
  const st={univ:"",prod:"",rebuild:false};
  const sh=modalShell("索引キャッシュを事前作成");
  sh.bd.appendChild(el("div","hint","University TM（必須）と Product TM（任意）から索引を作成します。初回は数分かかることがあります（完了までこのタブを閉じないでください）。"));
  sh.bd.appendChild(pathFieldK("University TM（.tmx・必須）","",'tmx',()=>st.univ,x=>{st.univ=x;}));
  sh.bd.appendChild(pathFieldK("Product TM（.tmx・任意）","",'tmx',()=>st.prod,x=>{st.prod=x;}));
  const fr=el("div","fld");const lab=el("label","toggle2");const cb=el("input");cb.type="checkbox";cb.onchange=()=>{st.rebuild=cb.checked;};lab.appendChild(cb);lab.appendChild(document.createTextNode(" 既存キャッシュがあっても再構築する"));fr.appendChild(lab);sh.bd.appendChild(fr);
  const run=el("button","primary","作成");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  run.onclick=()=>{if(!st.univ){toast("University TM を選択してください");return;}busy(run,true,"作成中…（数分）");api("/api/prebuild",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(run,false);if(r&&r.ok){toast("索引を作成しました（keys "+(r.keys||0)+"）");showLog("索引作成ログ",r.log);}else{toast("作成失敗："+((r&&r.error)||"不明"));if(r&&r.log)showLog("索引作成ログ",r.log);}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(run);sh.m.appendChild(sh.ft);overlay(sh.m);
}

function openWriteback(){
  const st={xliff:[],xliff_dir:"",master:"",project_tmx:"",customer:""};
  const sh=modalShell("TEP 結果を TM に書き戻す");
  sh.bd.appendChild(el("div","hint","確定（state=final / note に confirmed）の行だけを書き戻します。まず dry-run で件数を確認し、本実行の直前に書込先 TMX を日付きバックアップします。"));
  sh.bd.appendChild(listFieldK("XLIFF ファイル（複数可）","",'xliff',st.xliff));
  sh.bd.appendChild(pathFieldK("または XLIFF フォルダー（再帰）","",'dir',()=>st.xliff_dir,x=>{st.xliff_dir=x;}));
  sh.bd.appendChild(pathFieldK("書込先 Master TM（.tmx）","既定は Live_TM の Master。テストは scratch TMX を推奨。",'tmx',()=>st.master,x=>{st.master=x;}));
  sh.bd.appendChild(pathFieldK("書込先 Project TM（.tmx・任意）","",'tmx',()=>st.project_tmx,x=>{st.project_tmx=x;}));
  const prev=el("div","pre");prev.hidden=true;sh.bd.appendChild(prev);
  const dry=el("button","ghost","dry-run で確認");const run=el("button","primary","書き戻し（本実行）");run.disabled=true;const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  dry.onclick=()=>{busy(dry,true,"確認中…");api("/api/writeback",{method:"POST",body:JSON.stringify(Object.assign({},st,{dry_run:true}))}).then(r=>{busy(dry,false);if(r&&r.ok){prev.hidden=false;prev.textContent=r.log||"(出力なし)";run.disabled=false;toast("dry-run 完了。内容を確認して本実行してください");}else{toast("dry-run 失敗："+((r&&r.error)||"不明"));if(r&&r.log){prev.hidden=false;prev.textContent=r.log;}}}).catch(err=>{busy(dry,false);toast("通信エラー: "+err);});};
  run.onclick=()=>{busy(run,true,"書き戻し中…");api("/api/writeback",{method:"POST",body:JSON.stringify(Object.assign({},st,{dry_run:false}))}).then(r=>{busy(run,false);if(r&&r.ok){const bk=(r.backed_up&&r.backed_up.length)?("／バックアップ "+r.backed_up.length+" 件"):"";toast("書き戻しました"+bk);prev.hidden=false;prev.textContent=(r.log||"")+((r.backed_up&&r.backed_up.length)?("\n\nバックアップ:\n"+r.backed_up.join("\n")):"");run.disabled=true;refresh();}else{toast("書き戻し失敗："+((r&&r.error)||"不明"));if(r&&r.log){prev.hidden=false;prev.textContent=r.log;}}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(dry);sh.ft.appendChild(run);sh.m.appendChild(sh.ft);overlay(sh.m);
}

function openGlossary(){
  const st={source:[],html:[],xliff:[],confirmed_only:false,out:""};
  const sh=modalShell("UI Glossary を作成");
  sh.bd.appendChild(el("div","hint","ソース(.mdx)・生成HTML・確定XLIFF のいずれか1つ以上を指定。<out>.csv（Excel可）と .json を出力します。"));
  sh.bd.appendChild(listFieldK("ソース .mdx（複数可）","",'source',st.source));
  sh.bd.appendChild(listFieldK("生成した作業ファイル(HTML)（複数可）","",'html',st.html));
  sh.bd.appendChild(listFieldK("確定 XLIFF（複数可）","",'xliff',st.xliff));
  const fr=el("div","fld");const lab=el("label","toggle2");const cb=el("input");cb.type="checkbox";cb.onchange=()=>{st.confirmed_only=cb.checked;};lab.appendChild(cb);lab.appendChild(document.createTextNode(" XLIFF は確定行のみ使用する"));fr.appendChild(lab);sh.bd.appendChild(fr);
  sh.bd.appendChild(textField("出力プレフィックス（フルパス）","<prefix>.csv / .json を出力",st.out,v=>{st.out=v;},"C:\\...\\UI-Glossary"));
  const run=el("button","primary","作成");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  run.onclick=()=>{if(!st.out){toast("出力プレフィックスを入力してください");return;}busy(run,true,"作成中…");api("/api/glossary",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(run,false);if(r&&r.ok){toast("Glossary を作成しました");showLog("Glossary 結果",r.log,r.csv);}else{toast("作成失敗："+((r&&r.error)||"不明"));if(r&&r.log)showLog("Glossary ログ",r.log);}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(run);sh.m.appendChild(sh.ft);overlay(sh.m);
}

function openFileCompare(){
  const st={target:"",current:"",results:"",label:"",translatable_only:false};
  const sh=modalShell("ファイル比較 (EN: Current vs Target)");
  sh.bd.appendChild(el("div","hint","翻訳済みの英語ソース集合(Target)と現行(Current)を比較し、Excelレポートを出力します。Target 以外は既定値で可。"));
  sh.bd.appendChild(pathFieldK("Target（翻訳済みENフォルダー・必須）","",'dir',()=>st.target,x=>{st.target=x;}));
  sh.bd.appendChild(pathFieldK("Current（現行フォルダー・任意）","未指定なら既定",'dir',()=>st.current,x=>{st.current=x;}));
  sh.bd.appendChild(pathFieldK("出力フォルダー（任意）","未指定なら既定の Results",'dir',()=>st.results,x=>{st.results=x;}));
  sh.bd.appendChild(textField("ラベル（任意）","ファイル名の接尾辞",st.label,v=>{st.label=v;},"Fullset / Project"));
  const fr=el("div","fld");const lab=el("label","toggle2");const cb=el("input");cb.type="checkbox";cb.onchange=()=>{st.translatable_only=cb.checked;};lab.appendChild(cb);lab.appendChild(document.createTextNode(" 翻訳対象テキストのみで比較する"));fr.appendChild(lab);sh.bd.appendChild(fr);
  const run=el("button","primary","比較を実行");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  run.onclick=()=>{if(!st.target){toast("Target フォルダーを選択してください");return;}busy(run,true,"比較中…");api("/api/filecompare",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(run,false);if(r&&r.ok){toast("比較が完了しました");showLog("ファイル比較 結果",r.log,r.reveal);}else{toast("失敗："+((r&&r.error)||"不明"));showLog("ファイル比較 ログ",(r&&r.log)||((r&&r.error)||""),r&&r.reveal);}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(run);sh.m.appendChild(sh.ft);overlay(sh.m);
}
function openVersionCheck(){
  const st={en:"",ja:"",published:"",results:"",no_tm:false};
  const sh=modalShell("JA バージョンチェック");
  sh.bd.appendChild(el("div","hint","日本語版が英語版と同じバージョンかを判定し、Excelレポートを出力します。各フォルダー未指定なら既定値を使用。"));
  sh.bd.appendChild(pathFieldK("英語版フォルダー EN（任意）","",'dir',()=>st.en,x=>{st.en=x;}));
  sh.bd.appendChild(pathFieldK("日本語版フォルダー JA（任意）","",'dir',()=>st.ja,x=>{st.ja=x;}));
  sh.bd.appendChild(pathFieldK("Published JA（任意）","",'dir',()=>st.published,x=>{st.published=x;}));
  sh.bd.appendChild(pathFieldK("出力フォルダー（任意）","",'dir',()=>st.results,x=>{st.results=x;}));
  const fr=el("div","fld");const lab=el("label","toggle2");const cb=el("input");cb.type="checkbox";cb.onchange=()=>{st.no_tm=cb.checked;};lab.appendChild(cb);lab.appendChild(document.createTextNode(" TM参照を使わない"));fr.appendChild(lab);sh.bd.appendChild(fr);
  const run=el("button","primary","チェックを実行");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  run.onclick=()=>{busy(run,true,"チェック中…");api("/api/versioncheck",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(run,false);if(r&&r.ok){toast("チェックが完了しました");showLog("JA バージョンチェック 結果",r.log,r.reveal);}else{toast("失敗："+((r&&r.error)||"不明"));showLog("JA バージョンチェック ログ",(r&&r.log)||((r&&r.error)||""),r&&r.reveal);}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(run);sh.m.appendChild(sh.ft);overlay(sh.m);
}
const toolsPanel=document.getElementById("toolspanel");
if(toolsPanel){
  [["MTをHTMLに反映",openInject],["索引キャッシュを事前作成",openPrebuild],["TEP 結果を TM に書き戻す",openWriteback],["UI Glossary を作成",openGlossary],["ファイル比較 (EN)",openFileCompare],["JA バージョンチェック",openVersionCheck]].forEach(t=>{const b=el("button",null,t[0]);b.onclick=()=>{toolsPanel.hidden=true;t[1]();};toolsPanel.appendChild(b);});
  document.getElementById("toolsbtn").addEventListener("click",()=>{toolsPanel.hidden=!toolsPanel.hidden;});
  document.addEventListener("click",e=>{if(!e.target.closest("#toolswrap"))toolsPanel.hidden=true;});
}

// ===== 用語管理タブ =====
let TERMS=[]; const tstate={q:""};
function loadTerms(){return api("/api/terms").then(d=>{TERMS=(d&&d.rows)||[];renderTerms();}).catch(()=>{});}
function termMatch(t,q){if(!q)return true;const h=((t.source||"")+" "+(t.target||"")+" "+(t.note||"")+" "+(t.doc||"")+" "+(t.project||"")).toLowerCase();return h.includes(q);}
function renderTerms(){
  const q=tstate.q.trim().toLowerCase();
  const list=TERMS.filter(t=>termMatch(t,q));
  const tb=document.getElementById("trows");if(!tb)return;
  document.getElementById("tempty").hidden=list.length>0;
  document.getElementById("termcount").textContent=list.length+" / "+TERMS.length+" 件";
  tb.innerHTML=list.map(t=>'<tr data-id="'+esc(t.id)+'">'
    +'<td class="termtext">'+esc(t.source)+'</td>'
    +'<td class="termtext">'+esc(t.target)+'</td>'
    +'<td class="termtext meta">'+esc(t.example||"")+'</td>'
    +'<td class="termtext meta">'+esc(t.note||"")+'</td>'
    +'<td class="meta">'+esc(t.doc||"")+'</td>'
    +'<td class="meta">'+esc(t.project||"")+'</td>'
    +'<td class="meta">'+esc(t.updated||"")+'</td>'
    +'<td class="act"><button class="edit" type="button" data-id="'+esc(t.id)+'">編集</button></td></tr>').join("");
}
function openTermEdit(t){
  t=t||{};const st={id:t.id||"",source:t.source||"",target:t.target||"",example:t.example||"",note:t.note||"",doc:t.doc||"",project:t.project||""};
  const sh=modalShell(st.id?"用語の編集":"用語の追加");
  sh.bd.appendChild(textField("ソース（原文の用語）","",st.source,v=>{st.source=v;}));
  sh.bd.appendChild(textField("ターゲット（訳語）","",st.target,v=>{st.target=v;}));
  sh.bd.appendChild(textField("用例","",st.example,v=>{st.example=v;}));
  sh.bd.appendChild(textField("ノート","",st.note,v=>{st.note=v;}));
  sh.bd.appendChild(textField("ドキュメント名","",st.doc,v=>{st.doc=v;}));
  sh.bd.appendChild(textField("プロジェクト名","",st.project,v=>{st.project=v;}));
  const save=el("button","primary","保存");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  let del=null;
  if(st.id){del=el("button","ghost","削除");del.style.color="#c0392b";let armed=false;
    del.onclick=()=>{if(!armed){armed=true;del.textContent="本当に削除？（もう一度）";return;}busy(del,true,"削除中…");api("/api/term-delete",{method:"POST",body:JSON.stringify({id:st.id})}).then(()=>{closeOvl();toast("削除しました");loadTerms();}).catch(err=>{busy(del,false);toast("通信エラー: "+err);});};}
  save.onclick=()=>{if(!st.source.trim()){toast("ソースを入力してください");return;}busy(save,true,"保存中…");api("/api/term-save",{method:"POST",body:JSON.stringify(st)}).then(()=>{closeOvl();toast("保存しました");loadTerms();}).catch(err=>{busy(save,false);toast("通信エラー: "+err);});};
  if(del)sh.ft.appendChild(del);sh.ft.appendChild(cancel);sh.ft.appendChild(save);sh.m.appendChild(sh.ft);overlay(sh.m);
}
function openTermExtract(){
  const st={source:[],html:[],xliff:[],confirmed_only:false};
  const sh=modalShell("用語を抽出して登録");
  sh.bd.appendChild(el("div","hint","ソース(.mdx)/生成HTML/確定XLIFF から候補を抽出し、選んだ用語を用語集へ登録します。"));
  sh.bd.appendChild(listFieldK("ソース .mdx（複数可）","",'source',st.source));
  sh.bd.appendChild(listFieldK("生成した作業ファイル(HTML)（複数可）","",'html',st.html));
  sh.bd.appendChild(listFieldK("確定 XLIFF（複数可）","",'xliff',st.xliff));
  const doc=el("div","fld");doc.appendChild(el("label",null,"登録時のドキュメント名 / プロジェクト名（任意）"));
  const dwrap=el("div","row");const di=el("input");di.type="text";di.placeholder="ドキュメント名";const pi=el("input");pi.type="text";pi.placeholder="プロジェクト名";dwrap.appendChild(di);dwrap.appendChild(pi);doc.appendChild(dwrap);sh.bd.appendChild(doc);
  const box=el("div","brow");box.hidden=true;sh.bd.appendChild(box);
  const extract=el("button","ghost","候補を抽出");const reg=el("button","primary","選択を登録");reg.disabled=true;const cancel=el("button","ghost","閉じる");cancel.onclick=closeOvl;
  let cands=[];
  extract.onclick=()=>{busy(extract,true,"抽出中…");api("/api/term-extract",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(extract,false);if(!r||!r.ok){toast("抽出失敗："+((r&&r.error)||"不明"));return;}cands=r.candidates||[];box.hidden=false;box.innerHTML="";if(!cands.length){box.appendChild(el("div","hint","候補がありません。"));reg.disabled=true;return;}cands.forEach((c,i)=>{const row=el("label","it");row.innerHTML='<input type="checkbox" checked data-i="'+i+'"> '+esc(c.source)+' → '+esc(c.target||"（訳なし）");box.appendChild(row);});reg.disabled=false;toast(cands.length+" 件の候補");}).catch(err=>{busy(extract,false);toast("通信エラー: "+err);});};
  reg.onclick=()=>{const picks=[].slice.call(box.querySelectorAll('input[type=checkbox]')).filter(c=>c.checked).map(c=>cands[+c.getAttribute("data-i")]);if(!picks.length){toast("登録する用語を選んでください");return;}busy(reg,true,"登録中…");let n=0;const seq=picks.reduce((pr,c)=>pr.then(()=>api("/api/term-save",{method:"POST",body:JSON.stringify({source:c.source,target:c.target||"",doc:di.value,project:pi.value})}).then(()=>{n++;})),Promise.resolve());seq.then(()=>{busy(reg,false);closeOvl();toast(n+" 件を登録しました");loadTerms();}).catch(err=>{busy(reg,false);toast("通信エラー: "+err);});};
  sh.ft.appendChild(cancel);sh.ft.appendChild(extract);sh.ft.appendChild(reg);sh.m.appendChild(sh.ft);overlay(sh.m);
}
const termExportPanel=document.getElementById("termexportpanel");
if(termExportPanel){
  [["TSV","tsv"],["CSV","csv"],["Xlsx","xlsx"]].forEach(f=>{const b=el("button",null,f[0]);b.onclick=()=>{termExportPanel.hidden=true;api("/api/term-export",{method:"POST",body:JSON.stringify({fmt:f[1]})}).then(r=>{if(r&&r.ok){toast("エクスポートしました");showLog("エクスポート",r.out,r.out);}else{toast("失敗："+((r&&r.error)||"不明"));}}).catch(err=>toast("通信エラー: "+err));};termExportPanel.appendChild(b);});
  document.getElementById("termexportbtn").addEventListener("click",()=>{termExportPanel.hidden=!termExportPanel.hidden;});
  document.addEventListener("click",e=>{if(!e.target.closest("#termexportbtn")&&!e.target.closest("#termexportpanel"))termExportPanel.hidden=true;});
}
(function(){
  const tr=document.getElementById("trows");if(tr)tr.addEventListener("click",e=>{const b=e.target.closest("button.edit");if(!b)return;const t=TERMS.find(x=>x.id===b.getAttribute("data-id"));if(t)openTermEdit(t);});
  const tq=document.getElementById("tq");if(tq)tq.addEventListener("input",e=>{tstate.q=e.target.value;renderTerms();});
  const ta=document.getElementById("termadd");if(ta)ta.addEventListener("click",()=>openTermEdit(null));
  const tx=document.getElementById("termextract");if(tx)tx.addEventListener("click",openTermExtract);
})();
function switchView(v){
  document.getElementById("view-projects").hidden=(v!=="projects");
  document.getElementById("view-terms").hidden=(v!=="terms");
  var vtm=document.getElementById("view-tm");if(vtm)vtm.hidden=(v!=="tm");
  var vh=document.getElementById("view-history");if(vh)vh.hidden=(v!=="history");
  document.getElementById("tab-projects").setAttribute("aria-pressed",String(v==="projects"));
  document.getElementById("tab-terms").setAttribute("aria-pressed",String(v==="terms"));
  var ttm=document.getElementById("tab-tm");if(ttm)ttm.setAttribute("aria-pressed",String(v==="tm"));
  var th=document.getElementById("tab-history");if(th)th.setAttribute("aria-pressed",String(v==="history"));
  if(v==="terms")loadTerms();
  if(v==="tm")loadTM();
  if(v==="history")loadHistory();
}
document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click",()=>switchView(b.dataset.view)));
// ===== 履歴タブ: 操作の自動記録（日付・作業内容）＋メモ編集・削除 =====
var HIST=[];
function loadHistory(){return api("/api/history").then(function(d){HIST=(d&&d.rows)||[];renderHistory();}).catch(function(){});}
function renderHistory(){
  var q=(document.getElementById("hq")||{}).value||"";var ql=q.trim().toLowerCase();
  var list=HIST.filter(function(r){if(!ql)return true;return ((r.action||"")+" "+(r.detail||"")+" "+(r.memo||"")+" "+(r.project||"")).toLowerCase().indexOf(ql)>=0;});
  document.getElementById("hcount").textContent=list.length?(list.length+" 件"):"";
  document.getElementById("hempty").hidden=list.length>0;
  document.getElementById("hrows").innerHTML=list.map(function(r){
    var det=(r.detail||"")+(r.project?('　<span class="meta">['+esc(r.project)+']</span>'):"");
    return '<tr data-id="'+esc(r.id)+'">'
      +'<td class="meta">'+esc(r.at||"")+'</td>'
      +'<td>'+esc(r.action||"")+'</td>'
      +'<td class="ti">'+det+'</td>'
      +'<td class="memo"><input class="hmemo" value="'+esc(r.memo||"").replace(/"/g,"&quot;")+'" placeholder="メモ"></td>'
      +'<td class="act"><button class="edit" type="button" data-act="hsave" title="メモを保存">保存</button>'
      +'<button class="edit" type="button" data-act="hdel" title="この履歴を削除" style="margin-left:4px">削除</button></td></tr>';
  }).join("");
}
(function(){
  var q=document.getElementById("hq");if(q)q.addEventListener("input",renderHistory);
  var rf=document.getElementById("hrefresh");if(rf)rf.addEventListener("click",loadHistory);
  var tb=document.getElementById("hrows");if(tb)tb.addEventListener("click",function(e){
    var b=e.target.closest("button[data-act]");if(!b)return;var tr=b.closest("tr");if(!tr)return;var id=tr.getAttribute("data-id");
    if(b.getAttribute("data-act")==="hsave"){
      var memo=tr.querySelector(".hmemo").value;
      api("/api/history-save",{method:"POST",body:JSON.stringify({id:id,memo:memo})}).then(function(){toast("メモを保存しました");});
    }else if(b.getAttribute("data-act")==="hdel"){
      if(!confirm("この履歴を削除しますか？"))return;
      api("/api/history-delete",{method:"POST",body:JSON.stringify({id:id})}).then(function(){loadHistory();});
    }
  });
})();
// ===== TM タブ: TMエントリの一覧/検索/編集(EN+JA)/削除 =====
var TMLIST=[], TMCUR="";
function tmDate(d){var m=/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/.exec(d||"");return m?(m[1]+"-"+m[2]+"-"+m[3]+" "+m[4]+":"+m[5]):(d||"");}
function loadTM(){
  return api("/api/tm-list").then(function(d){
    TMLIST=(d&&d.rows)||[];
    var sel=document.getElementById("tmsel");if(!sel)return;
    sel.innerHTML=TMLIST.map(function(r){
      var lbl=r.name+" ["+r.role+"]"+(r.editable?(r.count!=null?(" ・"+r.count+"件"):""):" ・読み取り専用");
      return '<option value="'+esc(r.path)+'"'+(r.editable?"":" data-ro=\"1\"")+'>'+esc(lbl)+'</option>';
    }).join("");
    // 既定は編集可能な先頭TM
    var firstEditable=TMLIST.filter(function(r){return r.editable;})[0];
    TMCUR=(firstEditable?firstEditable.path:(TMLIST[0]?TMLIST[0].path:""));
    if(TMCUR)sel.value=TMCUR;
    loadTMEntries();
  }).catch(function(){});
}
function curTMrow(){return TMLIST.find(function(r){return r.path===TMCUR;});}
function loadTMEntries(){
  var q=(document.getElementById("tmq")||{}).value||"";
  var info=document.getElementById("tminfo");var row=curTMrow();
  if(info)info.textContent=row?(row.editable?"編集可":"読み取り専用（XTML/サイズ）"):"";
  if(!TMCUR){document.getElementById("tmrows").innerHTML="";document.getElementById("tmempty").hidden=false;return;}
  api("/api/tm-entries?tm="+encodeURIComponent(TMCUR)+"&q="+encodeURIComponent(q)).then(function(d){
    var rows=(d&&d.rows)||[];renderTMrows(rows);
  }).catch(function(){renderTMrows([]);});
}
function renderTMrows(rows){
  var tb=document.getElementById("tmrows");var row=curTMrow();var ed=(row&&row.editable);
  document.getElementById("tmcount").textContent=rows.length?(rows.length+" 件"):"";
  document.getElementById("tmempty").hidden=rows.length>0;
  tb.innerHTML=rows.map(function(r){
    var act=ed?('<button class="edit" type="button" data-act="tmedit">編集</button><button class="edit" type="button" data-act="tmdel" style="margin-left:4px">削除</button>'):'<span class="meta">読取専用</span>';
    return '<tr data-src="'+esc(r.src)+'" data-tgt="'+esc(r.tgt)+'">'
      +'<td class="ti">'+esc(r.src)+'</td><td class="ti">'+esc(r.tgt)+'</td>'
      +'<td class="meta">'+esc(tmDate(r.changedate))+'</td><td class="act">'+act+'</td></tr>';
  }).join("");
}
function openTmEdit(src,tgt){
  var row=curTMrow();if(!row||!row.editable)return;
  var m=el("div","modal");m.appendChild(el("h2",null,src?"TMエントリを編集":"TMエントリを追加"));
  var bd=el("div","bd");
  function fld(label,val){var f=el("div","fld");f.appendChild(el("label",null,label));var ta=el("textarea");ta.value=val||"";f.appendChild(ta);bd.appendChild(f);return ta;}
  var enI=fld("EN（原文）",src);var jaI=fld("JA（訳）",tgt);
  m.appendChild(bd);
  var ft=el("div","ft");var ok=el("button","primary",src?"保存":"追加");var c=el("button","ghost","キャンセル");
  ok.onclick=function(){
    var body={tm:TMCUR,old_src:src||"",old_tgt:tgt||"",src:enI.value,tgt:jaI.value};
    ok.disabled=true;
    api("/api/tm-save",{method:"POST",body:JSON.stringify(body)}).then(function(r){
      closeOvl();toast(r&&r.ok?"TMを更新しました（バックアップ作成済）":("更新失敗："+((r&&r.error)||"不明")));loadTMEntries();
    }).catch(function(e){ok.disabled=false;toast("通信エラー: "+e);});
  };
  c.onclick=closeOvl;ft.appendChild(ok);ft.appendChild(c);m.appendChild(ft);overlay(m);
}
(function(){
  var sel=document.getElementById("tmsel");if(sel)sel.addEventListener("change",function(){TMCUR=sel.value;loadTMEntries();});
  var q=document.getElementById("tmq");if(q)q.addEventListener("input",function(){clearTimeout(window._tmqT);window._tmqT=setTimeout(loadTMEntries,250);});
  var add=document.getElementById("tmaddbtn");if(add)add.addEventListener("click",function(){var row=curTMrow();if(!row||!row.editable){toast("編集可能なTMを選択してください");return;}openTmEdit("","");});
  var tb=document.getElementById("tmrows");if(tb)tb.addEventListener("click",function(e){
    var b=e.target.closest("button[data-act]");if(!b)return;var tr=b.closest("tr");if(!tr)return;
    var src=tr.getAttribute("data-src"),tgt=tr.getAttribute("data-tgt");
    if(b.getAttribute("data-act")==="tmedit"){openTmEdit(src,tgt);}
    else if(b.getAttribute("data-act")==="tmdel"){
      if(!confirm("このTMエントリを削除しますか？\\n"+src+" → "+tgt))return;
      api("/api/tm-delete",{method:"POST",body:JSON.stringify({tm:TMCUR,src:src,tgt:tgt})}).then(function(r){toast(r&&r.ok?"削除しました（バックアップ作成済）":("削除失敗："+((r&&r.error)||"不明")));loadTMEntries();});
    }
  });
})();

// ===== 親タブ: プロジェクト / TM Match Explorer（下位構造は各タブ内に維持） =====
// ===== 親タブ: プロジェクト ＋ 開いた記事ごとのプロジェクト名タブ（複数可） =====
var LS_TEP="kotonoha-tep-tabs";    // [{id,url,title}]
var LS_ACT="kotonoha-ptab-active"; // "proj" | "tep:<id>" | "demo"
function tepTabs(){try{return JSON.parse(localStorage.getItem(LS_TEP)||"[]")||[];}catch(e){return[];}}
function tepTabsSave(a){try{localStorage.setItem(LS_TEP,JSON.stringify(a));}catch(e){}}
function ptabActive(){try{return localStorage.getItem(LS_ACT)||"proj";}catch(e){return "proj";}}
function ptabActiveSave(v){try{localStorage.setItem(LS_ACT,v);}catch(e){}}
function renderPTabs(){
  var bar=document.getElementById("ptabs");if(!bar)return;
  var act=ptabActive();
  var html='<button class="ptab" data-ptab="proj" type="button" aria-pressed="'+(act==="proj")+'">プロジェクト</button>';
  var tabs=KT.served?tepTabs():[];
  if(tabs.length){
    tabs.forEach(function(t){var w="tep:"+t.id;
      html+='<button class="ptab" data-ptab="'+esc(w)+'" type="button" aria-pressed="'+(act===w)+'" title="'+esc((t.title||"")+" — 解析・Pre-translation済み／作業内容は自動保存")+'"><span class="lbl">'+esc(t.title||"(無題)")+'</span><span class="x" data-close="'+esc(t.id)+'" title="閉じる">×</span></button>';});
  } else if(KT.served){
    html+='<button class="ptab" data-ptab="demo" type="button" aria-pressed="'+(act==="demo")+'">TM-Match-Explorer</button>';
  }
  bar.innerHTML=html;
}
function viewIdFor(which){ if(which==="demo")return "tepview-__demo__"; if(which.indexOf("tep:")===0)return "tepview-"+which.slice(4); return ""; }
function ensureView(id,url){
  var box=document.getElementById("tepviews");if(!box||document.getElementById("tepview-"+id))return;
  var v=document.createElement("div");v.id="tepview-"+id;v.className="tepview";v.hidden=true;
  // ヒント/再読み込み/別タブ/保存して閉じる は TEPウィンドウ（iframe内）側のヘッダーへ移設。ここは iframe のみ。
  v.innerHTML='<iframe class="tepframe"></iframe>';
  box.appendChild(v);
  v.querySelector("iframe").src=url;
}
function ensureDemo(){
  var box=document.getElementById("tepviews");if(!box||document.getElementById("tepview-__demo__"))return;
  var v=document.createElement("div");v.id="tepview-__demo__";v.className="tepview";v.hidden=true;
  v.innerHTML='<iframe class="tepframe" src="/explorer"></iframe>';
  box.appendChild(v);
}
// TEPウィンドウ(iframe・同一オリジン)から「保存して閉じる」で現在のタブを閉じるために公開
window.closeActiveTEP=function(){var a=ptabActive();if(a.indexOf("tep:")===0)closeTEP(a.slice(4));};
function showPTab(which){
  ptabActiveSave(which);
  var proj=document.getElementById("ptab-proj");if(proj)proj.hidden=(which!=="proj");
  if(which==="demo")ensureDemo();
  var box=document.getElementById("tepviews");var tvid=viewIdFor(which);
  if(box)Array.prototype.forEach.call(box.children,function(v){v.hidden=(v.id!==tvid);});
  renderPTabs();
}
function openTEP(id,url,title){
  if(!KT.served)return;
  var tabs=tepTabs(),i=-1;
  tabs.forEach(function(t,k){if(t.id===id)i=k;});
  if(i<0){tabs.push({id:id,url:url,title:title||id});}
  else{tabs[i].url=url; if(title)tabs[i].title=title;}
  tepTabsSave(tabs);
  var ex=document.getElementById("tepview-"+id);
  if(ex){var fr=ex.querySelector("iframe"); if(fr)fr.src=url;}  // 既存ビューは最新内容に再読込（再実行後に反映）
  else{ensureView(id,url);}
  showPTab("tep:"+id);
}
function closeTEP(id){
  var tabs=tepTabs().filter(function(t){return t.id!==id;});tepTabsSave(tabs);
  var v=document.getElementById("tepview-"+id);if(v)v.remove();
  if(ptabActive()==="tep:"+id){showPTab(tabs.length?("tep:"+tabs[tabs.length-1].id):"demo");}
  else{renderPTabs();}
}
document.getElementById("ptabs").addEventListener("click",function(e){
  var x=e.target.closest(".x");if(x){e.stopPropagation();closeTEP(x.getAttribute("data-close"));return;}
  var b=e.target.closest(".ptab");if(!b)return;showPTab(b.getAttribute("data-ptab"));
});
// 記事「開く」→ プロジェクト名タブで表示（サーバーモード）。file:// は従来どおり別タブ。
(function(){var rowsEl=document.getElementById("rows");if(!rowsEl)return;
  rowsEl.addEventListener("click",function(e){
    var a=e.target.closest("a.open");if(!a)return;
    if(KT.served){e.preventDefault();var href=a.getAttribute("href");var m=href.match(/[?&]id=([^&]+)/);var id=m?decodeURIComponent(m[1]):href;openTEP(id,href,a.getAttribute("data-title")||"");}
  });
})();
// 生成物（中間生成物）の TEP を絶対パスで開く（別プロジェクト化せず /article?path= で配信）
function tepKey(s){var h=0;for(var i=0;i<(s||"").length;i++){h=(h*31+s.charCodeAt(i))|0;}return "f"+(h>>>0).toString(36);}
function openTEPbyPath(path,label){
  if(!KT.served||!path)return;
  openTEP(tepKey(path),"/article?path="+encodeURIComponent(path),label||path);
}
// 実行で生成された記事をプロジェクト名タブで自動表示（produced=[{title,html}]）
function openProduced(projName,produced){
  if(!KT.served||!produced||!produced.length)return;
  produced.forEach(function(a){
    var ti=(a&&a.title)||"";var html=(a&&a.html)||"";
    if(!html)return;
    var label=(produced.length>1)?((projName||"")+" ／ "+ti):(projName||ti);
    openTEPbyPath(html,label);
  });
}
function fmtSize(n){if(n==null)return "";if(n<1024)return n+" B";if(n<1048576)return (n/1024).toFixed(1)+" KB";return (n/1048576).toFixed(1)+" MB";}
// 『詳細』: プロジェクト行の下にサブセクションを開閉（作業サマリー＋_Details フォルダーの中間生成物）
function toggleDetails(pid,btn){
  var row=document.getElementById("detrow-"+pid),panel=document.getElementById("detpanel-"+pid);
  if(!row||!panel)return;
  var opening=row.hidden;
  row.hidden=!opening;
  if(btn)btn.setAttribute("aria-pressed",opening?"true":"false");
  if(opening){
    panel.innerHTML='<div class="empty">読み込み中…</div>';
    api("/api/details?id="+encodeURIComponent(pid)).then(function(d){renderDetails(pid,panel,d);})
      .catch(function(e){panel.innerHTML='<div class="empty">読み込みエラー: '+esc(String(e))+'</div>';});
  }
}
function renderDetails(pid,panel,d){
  if(!d||!d.ok){panel.innerHTML='<div class="empty">詳細を取得できませんでした'+(d&&d.error?("："+esc(d.error)):"")+'</div>';return;}
  var s=d.summary||{},arts=s.artifacts||[],h='';
  h+='<h3>作業サマリー</h3><div class="sumline">';
  h+='状態: <b>'+esc(s.status||"-")+'</b> ／ ソース <b>'+(s.sources||0)+'</b> 件 ／ メインTM <b>'+esc(s.main_tm||"未設定")+'</b> ／ Product TM <b>'+(s.product_tm?"有":"無")+'</b> ／ サブTM <b>'+(s.sub_tms||0)+'</b> 件';
  if(s.last_run)h+='<br>最終実行: <b>'+esc(s.last_run)+'</b>';
  if(arts.length){var seg=0,mt=0;arts.forEach(function(x){seg+=(x.segs||0);mt+=(x.mt||0);});
    h+='<br>生成記事: <b>'+arts.length+'</b> 件（計 '+seg+' セグメント ／ うち MT '+mt+'）';}
  h+='</div>';
  h+='<div class="ebar"><span style="color:var(--muted)">中間生成物（_kotonoha）:</span> <span class="dpath">'+esc(d.details_dir||"")+'</span> <button type="button" class="detopen" data-path="'+esc(d.details_dir||"")+'">フォルダーを開く</button></div>';
  if(!d.files||!d.files.length){
    h+='<div class="empty">まだ中間生成物はありません。「実行」すると、解析・Pre-translation の結果（作業ファイル ほか）がここに保存されます。</div>';
  }else{
    h+='<div class="flist">';
    d.files.forEach(function(f){
      h+='<div class="frow"><span class="fn">';
      h+=f.is_tep?('<a class="tep" data-path="'+esc(f.path)+'">'+esc(f.name)+(f.is_tep?' <span style="font-weight:400;color:var(--muted)">（開いて編集）</span>':'')+'</a>'):esc(f.name);
      h+='</span><span class="fm">'+esc(fmtSize(f.size))+(f.mtime?("　"+esc(f.mtime)):"")+'</span>';
      h+='<a class="reveal" data-reveal="'+esc(f.path)+'" title="保存場所を開く">開く</a></div>';
    });
    h+='</div>';
  }
  panel.innerHTML=h;
}
// 『出力』: 保存先を選択（2_For review / 3_Final / 任意フォルダー）してから出力
function openExportChoice(pid,btn){
  if(!KT.served)return;
  var chosen={mode:"review",path:""};
  var m=el("div","modal");m.appendChild(el("h2",null,"出力先を選択"));
  var bd=el("div","bd");
  bd.appendChild(el("p",null,"翻訳版（記事の訳文を適用した成果物）の保存先を選びます。"));
  var warn=el("p",null,"※ 2_For review に元ファイルと同名の成果物がある場合は上書きされます（元ファイルを残したいときは 3_Final か別フォルダーを選択）。");
  warn.style.cssText="color:var(--muted);font-size:12px;margin:-4px 0 4px";bd.appendChild(warn);
  var wrap=el("div","fld");
  [["review","2_For review（既定）"],["final","3_Final"],["other","その他のフォルダーを選択…"]].forEach(function(o){
    var lab=el("label","toggle2");lab.style.display="block";lab.style.margin="7px 0";
    var r=el("input");r.type="radio";r.name="exdest";r.value=o[0];if(o[0]==="review")r.checked=true;
    lab.appendChild(r);lab.appendChild(document.createTextNode(" "+o[1]));wrap.appendChild(lab);
    r.onclick=function(){chosen.mode=o[0];if(o[0]==="other"){openBrowser("dir",chosen.path||"",function(dir){chosen.path=dir;pc.textContent="選択: "+dir;pc.hidden=false;});}};
  });
  bd.appendChild(wrap);
  var pc=el("div","dpath");pc.hidden=true;pc.style.margin="4px 0 0";bd.appendChild(pc);
  m.appendChild(bd);
  var ft=el("div","ft");var go=el("button","primary","出力");
  go.onclick=function(){
    var body={id:pid};
    if(chosen.mode==="final")body.out_path="3_Final";
    else if(chosen.mode==="other"){if(!chosen.path){toast("フォルダーを選択してください");return;}body.out_path=chosen.path;}
    else body.out_path="2_For review";
    closeOvl();
    toast("出力中…");
    api("/api/export",{method:"POST",body:JSON.stringify(body)}).then(function(r){
      toast(r&&r.ok?("出力しました: "+(r.out_dir||"")+(r.applied!=null?("（適用 "+r.applied+"）"):"")):("出力失敗："+((r&&r.error)||"不明なエラー")));
    }).catch(function(err){toast("通信エラー: "+err);});
  };
  ft.appendChild(go);var c=el("button","ghost","キャンセル");c.onclick=closeOvl;ft.appendChild(c);
  m.appendChild(ft);overlay(m);
}
// 初期化: タブ復元＆アクティブ表示
(function(){ renderPTabs();
  var tabs=KT.served?tepTabs():[]; tabs.forEach(function(t){ensureView(t.id,t.url);});
  var act=ptabActive();
  if(act.indexOf("tep:")===0 && !tabs.some(function(t){return "tep:"+t.id===act;}))act="proj";
  if(act==="demo"&&!KT.served)act="proj";
  showPTab(act);
})();

if(KT.served){document.body.classList.add("served");var _tw=document.getElementById("toolswrap");if(_tw)_tw.hidden=false;var _tabs=document.getElementById("tabs");if(_tabs)_tabs.hidden=false;refresh();}
</script></body></html>"""
    return (tpl.replace("__DATA__", data).replace("__COLS__", colmeta)
               .replace("__KTCFG__", ktcfg).replace("__VER__", VERSION))

if a.cmd == "add":
    if not a.html:
        ap.error("--html required")
    t, s, m = meta_from_todo(a.html)
    upsert(projects, a.html, title=a.title or t, source=a.source or s,
           mt=a.mt if a.mt is not None else m, segs=a.segs)
    save(a.store, projects)
    print("registered:", a.html)

elif a.cmd == "add-batch":
    if not a.combined or not os.path.exists(a.combined):
        ap.error("--combined <combined.mt-todo.json> required")
    data = json.load(open(a.combined, encoding="utf-8-sig"))
    n = 0
    for art in data.get("articles", []):
        html = art.get("html", "")
        if not html:
            continue
        upsert(projects, html, title=art.get("title"), source=art.get("source"),
               segs=art.get("segs"), mt=art.get("mt"))
        n += 1
    save(a.store, projects)
    print("registered %d project(s) from batch" % n)

elif a.cmd == "create":
    pid = make_id(projects)
    projects.append({
        "id": pid, "type": "project", "name": a.name or pid, "status": "未解析",
        "sources": [], "main_tm": "", "product_tm": "", "sub_tms": [],
        "created": now(), "updated": now(),
    })
    save(a.store, projects)
    print(pid)

elif a.cmd == "add-source":
    p = find_by_id(projects, a.id)
    if not p or not a.path:
        print("ERROR: project not found or --path missing")
    else:
        p.setdefault("sources", []).append({"kind": (a.kind or "file"), "path": a.path})
        p["updated"] = now(); save(a.store, projects)
        print("added source (%s): %s" % (a.kind, a.path))

elif a.cmd == "set-main-tm":
    p = find_by_id(projects, a.id)
    if not p:
        print("ERROR: project not found")
    else:
        p["main_tm"] = a.path; p["updated"] = now(); save(a.store, projects)
        print("main TM set:", a.path)

elif a.cmd == "set-product-tm":
    p = find_by_id(projects, a.id)
    if not p:
        print("ERROR: project not found")
    else:
        p["product_tm"] = a.path; p["updated"] = now(); save(a.store, projects)
        print("product TM set:", a.path or "(cleared)")

elif a.cmd == "add-sub-tm":
    p = find_by_id(projects, a.id)
    if not p or not a.path:
        print("ERROR: project not found or --path missing")
    else:
        p.setdefault("sub_tms", []).append(a.path); p["updated"] = now(); save(a.store, projects)
        print("sub TM added:", a.path)

elif a.cmd == "new-tm":
    if not a.path:
        print("ERROR: --path required")
    elif os.path.exists(a.path):
        print("already exists:", a.path)
    else:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(a.path)), exist_ok=True)
            open(a.path, "w", encoding="utf-8", newline="\n").write(EMPTY_TMX)
            print("created empty TMX:", a.path)
        except Exception as e:
            print("ERROR creating TMX:", e)

elif a.cmd == "show":
    p = find_by_id(projects, a.id)
    if not p:
        print("ERROR: project not found:", a.id)
    else:
        print("  プロジェクト: %s  [%s]  id=%s" % (p.get("name", ""), p.get("status", ""), p.get("id", "")))
        srcs = p.get("sources", [])
        print("  ソース: %d 件" % len(srcs))
        for i, s in enumerate(srcs, 1):
            print("    %d. (%s) %s" % (i, s.get("kind", ""), s.get("path", "")))
        print("  メイン TM: %s" % (p.get("main_tm", "") or "(未設定)"))
        print("  Product TM: %s" % (p.get("product_tm", "") or "(未設定)"))
        subs = p.get("sub_tms", [])
        print("  サブ TM: %d 件" % len(subs))
        for i, s in enumerate(subs, 1):
            print("    %d. %s" % (i, s))
        print("  出力先: %s" % (p.get("out_dir", "") or "(未設定)"))
        print("  担当者: %s" % (p.get("assignee", "") or "(未設定)"))
        print("  期日  : %s" % (p.get("due", "") or "(未設定)"))
        print("  メモ  : %s" % (p.get("memo", "") or ""))

elif a.cmd == "srcs":
    p = find_by_id(projects, a.id)
    s = p.get("sources", []) if p else []
    if not s:
        print("   (ソース未追加)")
    else:
        for i, x in enumerate(s, 1):
            print("   %d. (%s) %s" % (i, x.get("kind", ""), x.get("path", "")))

elif a.cmd == "subs":
    p = find_by_id(projects, a.id)
    s = p.get("sub_tms", []) if p else []
    if not s:
        print("   (サブTM未追加)")
    else:
        for i, x in enumerate(s, 1):
            print("   %d. %s" % (i, x))

elif a.cmd == "undo-source":
    p = find_by_id(projects, a.id)
    if p and p.get("sources"):
        rm = p["sources"].pop(); p["updated"] = now(); save(a.store, projects)
        print("取消(ソース):", rm.get("path", ""))
    else:
        print("取り消すソースがありません")

elif a.cmd == "undo-sub-tm":
    p = find_by_id(projects, a.id)
    if p and p.get("sub_tms"):
        rm = p["sub_tms"].pop(); p["updated"] = now(); save(a.store, projects)
        print("取消(サブTM):", rm)
    else:
        print("取り消すサブTMがありません")

elif a.cmd == "set-outdir":
    p = find_by_id(projects, a.id)
    if p:
        p["out_dir"] = a.path; p["updated"] = now(); save(a.store, projects)
        print("出力先:", a.path)
    else:
        print("ERROR: project not found")

elif a.cmd == "set-assignee":
    p = find_by_id(projects, a.id)
    if p:
        p["assignee"] = a.assignee; p["updated"] = now(); save(a.store, projects)
        print("担当者:", a.assignee)
    else:
        print("ERROR: project not found")

elif a.cmd == "list":
    ps = ordered(projects)
    if a.active:
        ps = [p for p in ps if p.get("status") != "完了"]
    if a.status:
        ps = [p for p in ps if p.get("status") == a.status]
    if not ps:
        print("  (該当プロジェクトはありません)")
    else:
        for i, p in enumerate(ordered(projects), 1):
            if p not in ps:
                continue
            info = []
            if p.get("type") == "project":
                info.append("ソース%d" % len(p.get("sources", [])))
                info.append("サブTM%d" % len(p.get("sub_tms", [])))
            if p.get("segs") is not None: info.append("seg %s" % p["segs"])
            if p.get("mt") is not None:   info.append("MT %s" % p["mt"])
            extra = []
            if p.get("due"):  extra.append("期日 %s" % p["due"])
            if p.get("memo"): extra.append("memo:%s" % (p["memo"][:20]))
            nm = (p.get("title") or p.get("name") or "")
            print("  [%2d] %-5s %-26s %s  %s  %s"
                  % (i, p.get("status", ""), nm[:26],
                     p.get("updated", ""), " ".join(info), " ".join(extra)))

elif a.cmd == "get":
    ps = ordered(projects)
    if 1 <= a.index <= len(ps):
        print(ps[a.index - 1].get("html", ""))

elif a.cmd == "set-status":
    ps = ordered(projects)
    if 1 <= a.index <= len(ps) and a.status:
        ps[a.index - 1]["status"] = a.status
        save(a.store, projects)
        print("status set:", a.status)
    else:
        print("invalid index/status")

elif a.cmd == "set-memo":
    if a.id:
        p = find_by_id(projects, a.id)
        if p: p["memo"] = a.memo or ""; p["updated"] = now(); save(a.store, projects); print("memo set")
        else: print("ERROR: project not found")
    else:
        ps = ordered(projects)
        if 1 <= a.index <= len(ps):
            ps[a.index - 1]["memo"] = a.memo or ""; save(a.store, projects); print("memo set")
        else: print("invalid index")

elif a.cmd == "set-due":
    if a.id:
        p = find_by_id(projects, a.id)
        if p: p["due"] = a.due or ""; p["updated"] = now(); save(a.store, projects); print("due set")
        else: print("ERROR: project not found")
    else:
        ps = ordered(projects)
        if 1 <= a.index <= len(ps):
            ps[a.index - 1]["due"] = a.due or ""; save(a.store, projects); print("due set")
        else: print("invalid index")

elif a.cmd == "remove":
    ps = ordered(projects)
    if 1 <= a.index <= len(ps):
        tgt = ps[a.index - 1]
        if a.delete_file:
            for f in (tgt.get("html", ""), tgt.get("html", "") + ".mt-todo.json"):
                try:
                    if f and os.path.exists(f):
                        os.remove(f)
                except Exception as e:
                    print("WARN: could not delete", f, e)
        projects = [p for p in projects if p is not tgt]
        save(a.store, projects)
        print("removed" + (" (+file deleted)" if a.delete_file else ""))
    else:
        print("invalid index")

elif a.cmd == "idof":
    # print the id of the N-th listed row, but only if it is a saved project definition
    ps = ordered(projects)
    if 1 <= a.index <= len(ps) and ps[a.index - 1].get("type") == "project":
        print(ps[a.index - 1].get("id", ""))

elif a.cmd == "run":
    res = run_project(projects, a.store, a.id, out_path=a.path, engine=a.engine,
                      template=a.template, cache_dir=a.cache_dir, log=print)
    if not res.get("ok"):
        print("ERROR:", res.get("error")); sys.exit(res.get("rc") or 1)
    print("DONE. %d 記事を登録しました。 combined mt-todo: %s"
          % (res.get("registered", 0), res.get("combined", "")))

elif a.cmd == "export":
    res = export_project(projects, a.store, a.id, out_path=a.path, cache_dir=a.cache_dir,
                         mark_missing=a.mark_missing, log=print)
    if not res.get("ok"):
        print("ERROR:", res.get("error")); sys.exit(res.get("rc") or 1)
    print("DONE. 元形式の翻訳版を出力しました:", res.get("out_dir", ""))

elif a.cmd == "reinsert-json":
    out = a.out or (os.path.splitext(a.xliff)[0] + "_JA.json")
    res = reinsert_json(a.xliff, a.uidmap, out, json_path=a.path, confirmed_only=a.confirmed_only)
    if not res.get("ok"):
        print("ERROR:", res.get("error")); sys.exit(1)
    print("DONE. 翻訳済み JSON:", res["out"], "（適用 %d / filled %s）"
          % (res["applied"], res.get("filled")))

elif a.cmd == "dashboard":
    out = a.out or os.path.join(HERE, "_projects.html")
    open(out, "w", encoding="utf-8", newline="\n").write(dashboard_html(projects))
    print(out)

elif a.cmd == "serve":
    import http.server, socket, webbrowser, secrets, urllib.parse, subprocess

    TOKEN = secrets.token_urlsafe(16)
    STORE = a.store
    TERMSTORE = a.term_store or default_term_store()
    ENGINE, TEMPLATE, CACHE = a.engine, a.template, (a.cache_dir or read_cfg().get("CACHE", ""))
    try:
        import tkinter as _tkcheck  # noqa: F401
        HAS_TK = True
    except Exception:
        HAS_TK = False

    def pick_native(kind, multiple):
        """Open the native Windows file/folder dialog; return {available, paths}."""
        if not HAS_TK:
            return {"available": False, "paths": []}
        try:
            r = subprocess.run([sys.executable, "-c", TK_PICK, kind, "1" if multiple else "0"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace", timeout=600)
        except Exception as e:
            return {"available": True, "paths": [], "error": str(e)}
        if r.returncode == 2:
            return {"available": False, "paths": []}
        paths = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        return {"available": True, "paths": paths}

    def new_tmx_native():
        """ネイティブ保存ダイアログで保存先を選び、空の TMX を新規作成して返す。"""
        if not HAS_TK:
            return {"available": False}
        try:
            r = subprocess.run([sys.executable, "-c", TK_SAVE_TMX],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding="utf-8", errors="replace", timeout=600)
        except Exception as e:
            return {"available": True, "error": str(e)}
        if r.returncode == 2:
            return {"available": False}
        path = (r.stdout or "").strip()
        if not path:
            return {"available": True, "path": ""}   # キャンセル
        if not path.lower().endswith(".tmx"):
            path += ".tmx"
        try:
            if not os.path.exists(path):
                open(path, "w", encoding="utf-8", newline="\n").write(EMPTY_TMX)
            return {"available": True, "ok": True, "path": path}
        except Exception as e:
            return {"available": True, "ok": False, "error": str(e)}

    def browse_roots():
        cfg = read_cfg(); seen = []; out = []
        def add(name, path):
            if path and os.path.isdir(path):
                ap_ = os.path.abspath(path)
                if ap_ not in seen:
                    seen.append(ap_); out.append({"name": name, "path": ap_})
        for key, label in (("UNIV", "University TM"), ("PROD", "Product TM")):
            v = cfg.get(key, "")
            if v:
                add(label + " の場所", os.path.dirname(v))
        add("ソース/作業", cfg.get("SDIR", "") or cfg.get("SRC", ""))
        add("出力", cfg.get("ODIR", ""))
        add("CAT tool", os.path.abspath(os.path.join(HERE, "..")))
        add("ホーム", os.path.expanduser("~"))
        return out

    def list_dir(d, kind):
        d = os.path.abspath(d) if d else (browse_roots()[0]["path"] if browse_roots() else os.path.expanduser("~"))
        dirs, files = [], []
        try:
            for name in sorted(os.listdir(d), key=str.lower):
                full = os.path.join(d, name)
                try:
                    isdir = os.path.isdir(full)
                except OSError:
                    continue
                if isdir:
                    dirs.append({"name": name, "path": full})
                else:
                    low = name.lower()
                    _EXT = {"tmx": (".tmx",), "source": (".mdx", ".md"),
                            "xliff": (".xliff", ".xlf"), "html": (".html", ".htm"),
                            "json": (".json", ".jsonl")}
                    exts = _EXT.get(kind)
                    if exts and not low.endswith(exts):
                        continue
                    files.append({"name": name, "path": full})
        except Exception as e:
            return {"error": str(e), "dir": d}
        parent = os.path.dirname(d)
        if parent == d:
            parent = ""
        return {"dir": d, "parent": parent, "dirs": dirs, "files": files, "roots": browse_roots()}

    def _reskin_article(content, p):
        """任意の（古い）作業ファイル(HTML)を最新テンプレートに貼り替えて返す（SEGデータは流用）。
        これにより、過去に古いテンプレートで生成した記事も常に最新UIで表示できる。失敗時は None。"""
        import re as _re
        def _bal(s, j):
            depth = 0; k = j; instr = False; esc = False; q = ''
            while k < len(s):
                c = s[k]
                if instr:
                    if esc: esc = False
                    elif c == '\\': esc = True
                    elif c == q: instr = False
                else:
                    if c == '"' or c == "'": instr = True; q = c
                    elif c == '[': depth += 1
                    elif c == ']':
                        depth -= 1
                        if depth == 0: return k
                k += 1
            return -1
        def _seg_span(s):
            i = s.find("const SEG = [")
            if i < 0: return (None, -1, -1)
            j = s.find("[", i); e = _bal(s, j)
            if e < 0: return (None, -1, -1)
            return (s[j:e + 1], i, e)
        try:
            seg, _si, _se = _seg_span(content)
            if not seg:
                return None
            tpl_path = TEMPLATE or os.path.join(HERE, "TM-Match-Explorer-demo.html")
            tpl = open(tpl_path, encoding="utf-8").read()
            tseg, ti, te = _seg_span(tpl)
            if tseg is None:
                return None
            semi = tpl.find(";", te)
            if semi < 0:
                return None
            out = tpl[:ti] + "const SEG = " + seg + tpl[semi:]
            title = (p.get("title") or p.get("name") or "") if p else ""
            out = out.replace('DomoStats Connector <span class="demoflag">DEMO</span>', _html.escape(title))
            mm = _re.search(r"const META = ([\s\S]*?);\s*/\*__META__\*/", content)
            if mm:
                meta_js = mm.group(1)
            else:
                pp = p or {}
                meta = {"source": {"name": os.path.basename(pp.get("source", "")), "path": pp.get("source", "")},
                        "output": {"name": os.path.basename(pp.get("html", "")), "path": pp.get("html", "")},
                        "tms": [], "project": {"name": pp.get("project", ""), "detail": ""}, "generated": ""}
                meta_js = json.dumps(meta, ensure_ascii=False)
            out = _re.sub(r"const META = [\s\S]*?;\s*/\*__META__\*/",
                          lambda m: "const META = " + meta_js + ";  /*__META__*/", out, count=1)
            return out
        except Exception:
            return None

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass  # quiet

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _auth(self):
            return self.headers.get("X-KT-Token", "") == TOKEN

        def _serve_article(self, rid):
            """Serve a registered artifact HTML over http with the KT token injected,
            so its term pane can call /api/* (file:// 配信では不可)。登録済み html に限定。
            内容は生成された .html を**そのまま**配信する（貼り替えはしない＝ファイルと完全一致）。"""
            p = find_by_row_id(load(STORE), rid)
            hp = p.get("html", "") if p else ""
            if not (hp and os.path.isfile(hp)):
                self._send(404, {"error": "article not found"}); return
            try:
                content = open(hp, encoding="utf-8").read()
            except Exception as e:
                self._send(404, {"error": str(e)}); return
            kt = {"served": True, "token": TOKEN,
                  "doc": p.get("title", ""), "project": p.get("project", "")}
            self._send(200, "<script>window.__KT=%s;</script>%s"
                       % (json.dumps(kt, ensure_ascii=False), content),
                       "text/html; charset=utf-8")

        def _serve_article_path(self, path):
            """生成物（中間生成物）の作業ファイル(HTML)を絶対パスで配信。
            内容は生成された .html を**そのまま**配信（KTトークンのみ付与＝ファイルと完全一致）。
            既知プロジェクトルート配下 or 旧 Kotonoha-out 配下のパスに限定（安全対策）。"""
            if not path:
                self._send(404, {"error": "article not found"}); return
            path = os.path.abspath(path)
            if not (os.path.isfile(path) and path.lower().endswith(".html")):
                self._send(404, {"error": "article not found"}); return
            projs = load(STORE)
            owner = None; art = None
            for pr in projs:
                for a in (pr.get("artifacts") or []):
                    if a.get("html") and os.path.abspath(a["html"]) == path:
                        owner = pr; art = a; break
                if owner:
                    break
            roots = []
            for pr in projs:
                s0 = _first_source_path(pr)
                if s0:
                    roots.append(os.path.abspath(project_root_for(s0)))
            roots.append(os.path.abspath(os.path.join(HERE, "..", "Kotonoha-out")))
            allowed = any(r and (path == r or path.startswith(r + os.sep)) for r in roots)
            if not allowed:
                self._send(403, {"error": "forbidden"}); return
            try:
                content = open(path, encoding="utf-8").read()
            except Exception as e:
                self._send(404, {"error": str(e)}); return
            pseudo = {"title": (art.get("title") if art else
                                os.path.splitext(os.path.basename(path))[0]),
                      "name": (owner.get("name") if owner else ""),
                      "source": (art.get("source") if art else ""),
                      "html": path,
                      "project": (owner.get("name") if owner else "")}
            # Concordance の既定検索対象 = この記事の所属プロジェクトの TM（メイン/サブ/Product）
            kt_tms = []
            if owner:
                _seen = set()
                for _p in ([owner.get("main_tm", ""), owner.get("product_tm", "")] + list(owner.get("sub_tms") or [])):
                    if _p and os.path.abspath(_p).lower() not in _seen and os.path.isfile(_p):
                        _seen.add(os.path.abspath(_p).lower())
                        kt_tms.append({"path": os.path.abspath(_p), "name": os.path.basename(_p)})
            kt = {"served": True, "token": TOKEN,
                  "doc": pseudo.get("title", ""), "project": pseudo.get("project", ""),
                  "tms": kt_tms}
            self._send(200, "<script>window.__KT=%s;</script>%s"
                       % (json.dumps(kt, ensure_ascii=False), content),
                       "text/html; charset=utf-8")

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/", "/index.html"):
                self._send(200, dashboard_html(load(STORE), served=True, token=TOKEN),
                           "text/html; charset=utf-8")
                return
            if u.path == "/article":
                q = urllib.parse.parse_qs(u.query)
                pth = q.get("path", [""])[0]
                if pth:
                    self._serve_article_path(pth)
                else:
                    self._serve_article(q.get("id", [""])[0])
                return
            if u.path == "/explorer":
                # TM-Match-Explorer 親タブの既定表示: 空の翻訳／サマリー（プロジェクトが無いとき）
                import re as _re
                tpl = TEMPLATE or os.path.join(HERE, "TM-Match-Explorer-demo.html")
                try:
                    content = open(tpl, encoding="utf-8").read()
                except Exception as e:
                    self._send(404, {"error": str(e)}); return
                # デモデータを空に（SEG=[]・最小META）＝空の翻訳/サマリーを表示
                content = _re.sub(r"const SEG = \[[\s\S]*?\n\];", "const SEG = [];", content, count=1)
                _meta = {"source": {"name": "", "path": ""}, "output": {"name": "", "path": ""},
                         "tms": [], "project": {"name": "", "detail": ""}, "generated": "", "runMT": True}
                content = _re.sub(r"const META = [\s\S]*?;\s*/\*__META__\*/",
                                  "const META = " + json.dumps(_meta, ensure_ascii=False) + ";  /*__META__*/",
                                  content, count=1)
                content = content.replace('DomoStats Connector <span class="demoflag">DEMO</span>', "（プロジェクト未選択）")
                kt = {"served": True, "token": TOKEN, "doc": "", "project": ""}
                self._send(200, "<script>window.__KT=%s;</script>%s"
                           % (json.dumps(kt, ensure_ascii=False), content),
                           "text/html; charset=utf-8")
                return
            if u.path.startswith("/api/"):
                if not self._auth():
                    self._send(403, {"error": "forbidden"}); return
                if u.path == "/api/projects":
                    self._send(200, {"rows": build_rows(load(STORE), served=True)}); return
                if u.path == "/api/history":
                    self._send(200, {"rows": list(reversed(load_history(STORE)))}); return
                if u.path == "/api/details":
                    q = urllib.parse.parse_qs(u.query)
                    self._send(200, project_details(load(STORE), q.get("id", [""])[0])); return
                if u.path == "/api/browse":
                    q = urllib.parse.parse_qs(u.query)
                    self._send(200, list_dir(q.get("dir", [""])[0], q.get("kind", ["source"])[0])); return
                if u.path == "/api/terms":
                    q = urllib.parse.parse_qs(u.query)
                    seg = q.get("seg", [""])[0]
                    terms = load_terms(TERMSTORE)
                    self._send(200, {"rows": (terms_for_segment(terms, seg) if seg else terms)}); return
                if u.path == "/api/tm-list":
                    self._send(200, {"rows": tm_list_rows(load(STORE))}); return
                if u.path == "/api/tm-entries":
                    import tm_io
                    q = urllib.parse.parse_qs(u.query)
                    tm = q.get("tm", [""])[0]
                    if os.path.abspath(tm).lower() not in _tm_known_paths(load(STORE)):
                        self._send(403, {"error": "unknown TM"}); return
                    try:
                        rows = tm_io.search(tm, q.get("q", [""])[0], int(q.get("limit", ["500"])[0] or 500))
                        self._send(200, {"ok": True, "rows": rows})
                    except Exception as e:
                        self._send(200, {"ok": False, "error": str(e), "rows": []})
                    return
                if u.path == "/api/conc-status":
                    import tm_concordance
                    q = urllib.parse.parse_qs(u.query)
                    known = _tm_known_paths(load(STORE)); cd = _conc_cache_dir()
                    out = []
                    for tm in (q.get("tms", [""])[0] or "").split("\n"):
                        tm = tm.strip()
                        if not tm or os.path.abspath(tm).lower() not in known:
                            continue
                        out.append({"path": os.path.abspath(tm), "name": os.path.basename(tm),
                                    "built": tm_concordance.is_built(tm, cd)})
                    self._send(200, {"rows": out}); return
                if u.path == "/api/conc-search":
                    import tm_concordance
                    q = urllib.parse.parse_qs(u.query)
                    known = _tm_known_paths(load(STORE))
                    tms = [t.strip() for t in (q.get("tms", [""])[0] or "").split("\n")
                           if t.strip() and os.path.abspath(t.strip()).lower() in known]
                    res = tm_concordance.search(
                        tms, q.get("q", [""])[0], q.get("field", ["both"])[0],
                        q.get("case", ["0"])[0] == "1", q.get("regex", ["0"])[0] == "1",
                        q.get("mode", ["and"])[0], int(q.get("limit", ["300"])[0] or 300),
                        _conc_cache_dir())
                    self._send(200, res); return
                if u.path == "/api/load-edits":
                    q = urllib.parse.parse_qs(u.query)
                    art = q.get("art", [""])[0] or "untitled"
                    safe = ("".join(("_" if c in '\\/:*?"<>|' else c) for c in art)[:120]) or "untitled"
                    fp = os.path.join(os.path.dirname(os.path.abspath(STORE)), "_wip", safe + ".json")
                    if os.path.isfile(fp):
                        try:
                            rec = json.load(open(fp, encoding="utf-8"))
                            self._send(200, {"ok": True, "edits": rec.get("edits", {}),
                                             "confirms": rec.get("confirms", {}),
                                             "savedAt": rec.get("savedAt", "")}); return
                        except Exception as e:
                            self._send(200, {"ok": False, "error": str(e)}); return
                    self._send(200, {"ok": True, "edits": {}, "confirms": {}, "savedAt": ""}); return
            self._send(404, {"error": "not found"})

        def do_POST(self):
            u = urllib.parse.urlparse(self.path)
            if not u.path.startswith("/api/") or not self._auth():
                self._send(403, {"error": "forbidden"}); return
            try:
                n = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception as e:
                self._send(400, {"error": "bad request: %s" % e}); return
            if u.path == "/api/pick":
                self._send(200, pick_native(payload.get("kind", "source"),
                                            bool(payload.get("multiple")))); return
            if u.path == "/api/new-tmx":
                self._send(200, new_tmx_native()); return
            if u.path == "/api/save-edits":
                # TEP の作業途中保存（編集・確定）をサーバー側 _wip/<art>.json に保存
                try:
                    wipdir = os.path.join(os.path.dirname(os.path.abspath(STORE)), "_wip")
                    os.makedirs(wipdir, exist_ok=True)
                    art = payload.get("art", "") or "untitled"
                    safe = ("".join(("_" if c in '\\/:*?"<>|' else c) for c in art)[:120]) or "untitled"
                    rec = {"art": art, "edits": payload.get("edits", {}) or {},
                           "confirms": payload.get("confirms", {}) or {},
                           "savedAt": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                    json.dump(rec, open(os.path.join(wipdir, safe + ".json"), "w", encoding="utf-8"),
                              ensure_ascii=False, indent=1)
                    self._send(200, {"ok": True, "savedAt": rec["savedAt"]})
                except Exception as e:
                    self._send(200, {"ok": False, "error": str(e)})
                return
            if u.path == "/api/open":
                # サマリーの「保存場所を開く」: 指定パス（ファイル/フォルダ）の保存先をエクスプローラーで開く
                tgt = payload.get("path", "") or ""
                try:
                    folder = tgt if os.path.isdir(tgt) else os.path.dirname(tgt)
                    if folder and os.path.isdir(folder):
                        os.startfile(folder)  # Windows: エクスプローラーで開く
                        self._send(200, {"ok": True, "opened": folder})
                    else:
                        self._send(200, {"ok": False, "error": "folder not found: %s" % (folder or tgt)})
                except Exception as e:
                    self._send(200, {"ok": False, "error": str(e)})
                return
            if u.path == "/api/filecompare":
                self._send(200, filecompare_run(target=payload.get("target", ""),
                                                current=payload.get("current", ""),
                                                results=payload.get("results", ""),
                                                label=payload.get("label", ""),
                                                translatable_only=bool(payload.get("translatable_only")),
                                                capture=True)); return
            if u.path == "/api/versioncheck":
                self._send(200, versioncheck_run(en=payload.get("en", ""),
                                                 ja=payload.get("ja", ""),
                                                 published=payload.get("published", ""),
                                                 results=payload.get("results", ""),
                                                 no_tm=bool(payload.get("no_tm")),
                                                 capture=True)); return
            if u.path == "/api/create":
                projs = load(STORE)
                pid = create_project_full(projs, payload.get("name", ""),
                                          sources=payload.get("sources", []),
                                          main_tm=payload.get("main_tm", ""),
                                          product_tm=payload.get("product_tm", ""),
                                          sub_tms=payload.get("sub_tms", []),
                                          run_mt=payload.get("run_mt", True))
                save(STORE, projs)
                log_history(STORE, "プロジェクト作成", "ソース %d 件" % len(payload.get("sources", []) or []), payload.get("name", ""))
                self._send(200, {"id": pid}); return
            if u.path == "/api/run":
                projs = load(STORE)
                res = run_project(projs, STORE, payload.get("id", ""), engine=ENGINE,
                                  template=TEMPLATE, cache_dir=CACHE, log=lambda *x: None,
                                  capture=True)
                if res.get("ok"):
                    log_history(STORE, "実行（解析＋Pre-translation）", "生成 %d 件" % (res.get("registered", 0)), res.get("project", ""))
                self._send(200, res); return
            if u.path == "/api/export":
                projs = load(STORE)
                _pn = (find_by_id(projs, payload.get("id", "")) or {}).get("name", "")
                res = export_project(projs, STORE, payload.get("id", ""),
                                     out_path=payload.get("out_path", ""), cache_dir=CACHE,
                                     mark_missing=bool(payload.get("mark_missing")),
                                     log=lambda *x: None, capture=True)
                if res.get("ok"):
                    log_history(STORE, "出力", "%s（適用 %s）" % (res.get("out_dir", ""), res.get("applied", "-")), _pn)
                self._send(200, res); return
            if u.path == "/api/set-status":
                projs = load(STORE)
                _pn = (find_by_row_id(projs, payload.get("id", "")) or {}).get("name", "")
                log_history(STORE, "状態を変更", "→ %s" % payload.get("status", ""), _pn)
                self._send(200, update_field(projs, STORE, payload.get("id", ""),
                                             "status", payload.get("status", ""))); return
            if u.path == "/api/set-memo":
                projs = load(STORE)
                self._send(200, update_field(projs, STORE, payload.get("id", ""),
                                             "memo", payload.get("memo", ""))); return
            if u.path == "/api/set-due":
                projs = load(STORE)
                self._send(200, update_field(projs, STORE, payload.get("id", ""),
                                             "due", payload.get("due", ""))); return
            if u.path == "/api/remove":
                projs = load(STORE)
                _pn = (find_by_row_id(projs, payload.get("id", "")) or {}).get("name", "")
                log_history(STORE, "プロジェクト削除", ("ファイルも削除" if payload.get("delete_file") else "台帳のみ"), _pn)
                self._send(200, remove_project(projs, STORE, payload.get("id", ""),
                                               bool(payload.get("delete_file")))); return
            if u.path == "/api/inject":
                _r = inject_mt_run(payload.get("mode", "single"),
                                   html=payload.get("html", ""), mt=payload.get("mt", ""),
                                   combined_todo=payload.get("combined_todo", ""),
                                   combined_mt=payload.get("combined_mt", ""), capture=True)
                log_history(STORE, "MTを反映", os.path.basename(payload.get("html", "") or payload.get("combined_todo", "")))
                self._send(200, _r); return
            if u.path == "/api/prebuild":
                self._send(200, prebuild_index(payload.get("univ", ""), prod=payload.get("prod", ""),
                                               cache_dir=payload.get("cache_dir", "") or CACHE,
                                               rebuild=bool(payload.get("rebuild")), capture=True)); return
            if u.path == "/api/writeback":
                _wb = writeback_run(xliff=payload.get("xliff", []),
                                    xliff_dir=payload.get("xliff_dir", ""),
                                    master=payload.get("master", ""),
                                    project_tmx=payload.get("project_tmx", ""),
                                    customer=payload.get("customer", ""),
                                    dry_run=bool(payload.get("dry_run", True)),
                                    backup=True, capture=True)
                if not payload.get("dry_run", True):
                    log_history(STORE, "TM書き戻し", payload.get("customer", "") or "Master")
                self._send(200, _wb); return
            if u.path == "/api/glossary":
                self._send(200, glossary_run(source=payload.get("source", []),
                                             source_dir=payload.get("source_dir", ""),
                                             html=payload.get("html", []), xliff=payload.get("xliff", []),
                                             xliff_dir=payload.get("xliff_dir", ""),
                                             confirmed_only=bool(payload.get("confirmed_only")),
                                             tmx=payload.get("tmx", ""), product_tmx=payload.get("product_tmx", ""),
                                             cache_dir=payload.get("cache_dir", "") or CACHE,
                                             out=payload.get("out", ""), capture=True)); return
            if u.path == "/api/reveal":
                pth = payload.get("path", "")
                try:
                    tgt = pth if os.path.isdir(pth) else os.path.dirname(pth)
                    os.startfile(tgt)   # Windows: open the folder in Explorer
                    self._send(200, {"ok": True}); return
                except Exception as e:
                    self._send(200, {"ok": False, "error": str(e)}); return
            if u.path == "/api/term-save":
                terms = load_terms(TERMSTORE)
                rec = term_save(terms, payload)
                save_terms(TERMSTORE, terms)
                log_history(STORE, ("用語を編集" if payload.get("id") else "用語を追加"),
                            "%s → %s" % (payload.get("source", ""), payload.get("target", "")))
                self._send(200, {"ok": True, "term": rec}); return
            if u.path == "/api/term-delete":
                terms = load_terms(TERMSTORE)
                n = term_delete(terms, payload.get("id", ""))
                save_terms(TERMSTORE, terms)
                log_history(STORE, "用語を削除", payload.get("id", ""))
                self._send(200, {"ok": True, "deleted": n}); return
            if u.path in ("/api/tm-save", "/api/tm-delete"):
                import tm_io
                tm = payload.get("tm", "")
                ap = os.path.abspath(tm)
                rows = tm_list_rows(load(STORE), with_count=False)
                row = next((r for r in rows if r["path"].lower() == ap.lower()), None)
                if not row:
                    self._send(403, {"error": "unknown TM"}); return
                if not row.get("editable"):
                    self._send(200, {"ok": False, "error": "このTMは編集できません（XTM 読み取り専用／サイズ超過）"}); return
                try:
                    if u.path == "/api/tm-save":
                        res = tm_io.update(ap, payload.get("old_src", ""), payload.get("old_tgt", ""),
                                           payload.get("src", ""), payload.get("tgt", ""))
                        if res.get("ok"):
                            log_history(STORE, "TMを編集", "%s: %s → %s" % (row["name"], payload.get("src", ""), payload.get("tgt", "")))
                    else:
                        res = tm_io.delete(ap, payload.get("src", ""), payload.get("tgt", ""))
                        if res.get("ok"):
                            log_history(STORE, "TMエントリを削除", "%s: %s" % (row["name"], payload.get("src", "")))
                    self._send(200, res)
                except Exception as e:
                    self._send(200, {"ok": False, "error": str(e)})
                return
            if u.path == "/api/conc-build":
                import tm_concordance
                known = _tm_known_paths(load(STORE)); cd = _conc_cache_dir()
                results = []
                for tm in (payload.get("tms") or []):
                    if os.path.abspath(tm).lower() not in known:
                        results.append({"path": tm, "name": os.path.basename(tm), "ok": False, "error": "unknown TM"}); continue
                    try:
                        r = tm_concordance.build(tm, cd)
                        results.append({"path": os.path.abspath(tm), "name": os.path.basename(tm),
                                        "ok": r.get("ok"), "count": r.get("count"), "error": r.get("error", "")})
                    except Exception as e:
                        results.append({"path": tm, "name": os.path.basename(tm), "ok": False, "error": str(e)})
                _okn = [r["name"] for r in results if r.get("ok")]
                if _okn:
                    log_history(STORE, "Concordance索引を作成", "、".join(_okn))
                self._send(200, {"results": results}); return
            if u.path == "/api/history-save":
                self._send(200, {"ok": history_update(STORE, payload.get("id", ""), payload)}); return
            if u.path == "/api/history-delete":
                self._send(200, {"ok": True, "deleted": history_delete(STORE, payload.get("id", ""))}); return
            if u.path == "/api/term-export":
                terms = load_terms(TERMSTORE)
                fmt = (payload.get("fmt") or "tsv").lower()
                out = payload.get("out", "") or os.path.join(
                    os.path.dirname(TERMSTORE), "terms-export." + fmt)
                try:
                    res = export_terms(terms, out, fmt)
                except Exception as e:
                    res = {"ok": False, "error": str(e)}
                self._send(200, res); return
            if u.path == "/api/term-extract":
                import tempfile
                outp = os.path.join(tempfile.mkdtemp(prefix="kt_ext_"), "g")
                res = glossary_run(source=payload.get("source", []), html=payload.get("html", []),
                                   xliff=payload.get("xliff", []), xliff_dir=payload.get("xliff_dir", ""),
                                   confirmed_only=bool(payload.get("confirmed_only")),
                                   cache_dir=CACHE, out=outp, capture=True)
                cands = []
                if res.get("ok"):
                    try:
                        d = json.load(open(outp + ".json", encoding="utf-8-sig"))
                        cands = [{"source": t.get("en", ""), "target": t.get("ja", ""),
                                  "type": t.get("type", "")} for t in d.get("terms", []) if t.get("en")]
                    except Exception as e:
                        res = {"ok": False, "error": "候補の読込に失敗: %s" % e}
                self._send(200, {"ok": res.get("ok", False), "error": res.get("error", ""),
                                 "candidates": cands}); return
            self._send(404, {"error": "not found"})

    port = a.port
    for cand in range(a.port, a.port + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", cand)); port = cand; break
            except OSError:
                continue
    url = "http://127.0.0.1:%d/" % port
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print("=" * 54)
    print(" Kotonoha ダッシュボード（サーバーモード）起動")
    print("   %s" % url)
    print("   ブラウザが自動で開きます。作成・実行がブラウザから行えます。")
    print("   終了するには、このウィンドウで Ctrl+C を押してください。")
    print("=" * 54, flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止しました。")
    finally:
        httpd.server_close()
