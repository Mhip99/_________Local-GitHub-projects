# -*- coding: utf-8 -*-
"""Project registry + dashboard for the Kotonoha beta5 launcher.

Records each analyzed / Pre-translated article (過去のプロジェクトリスト) so work
can be resumed anytime: re-opening a project's HTML restores the TEP edits/confirms
the browser saved in localStorage. The project list is shown in its own browser tab
via a generated dashboard (_projects.html), separate from the TEP HTML.

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

def upsert(projects, html, title=None, source=None, segs=None, mt=None):
    key = ncase(html)
    for p in projects:
        if ncase(p.get("html", "")) == key:
            if title is not None:  p["title"] = title
            if source is not None: p["source"] = source
            if segs is not None:   p["segs"] = segs
            if mt is not None:     p["mt"] = mt
            p["updated"] = now()
            return False
    projects.append({
        "id": make_id(projects),
        "html": html,
        "title": title or os.path.splitext(os.path.basename(html))[0],
        "source": source or "", "segs": segs, "mt": mt,
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
             '  <header creationtool="Kotonoha" creationtoolversion="beta5" segtype="sentence" '
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


def create_project_full(projects, name, sources=None, main_tm="", product_tm="", sub_tms=None):
    """Create a definition in one shot (used by the serve API). Caller saves."""
    pid = make_id(projects)
    projects.append({
        "id": pid, "type": "project", "name": name or pid, "status": "未解析",
        "sources": [{"kind": (s.get("kind") or "file"), "path": s.get("path", "")}
                    for s in (sources or []) if s.get("path")],
        "main_tm": main_tm or "", "product_tm": product_tm or "",
        "sub_tms": [t for t in (sub_tms or []) if t],
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


def run_project(projects, store, pid, out_path="", engine="", template="",
                cache_dir="", log=print, capture=False):
    """Analyze + Pre-translate a saved definition. Shared by the `run` CLI command
    and the serve API. Returns a result dict; registers produced articles and saves."""
    import subprocess
    p = find_by_id(projects, pid)
    if not p or p.get("type") != "project":
        return {"ok": False, "error": "project definition not found: %s" % pid}
    srcs = p.get("sources", [])
    main_tm = p.get("main_tm", "")
    if not srcs:
        return {"ok": False, "error": "project has no sources"}
    if not main_tm or not os.path.exists(main_tm):
        return {"ok": False, "error": "main TM not found: %s" % (main_tm or "(未設定)")}

    entries = expand_sources(srcs, (".mdx", ".md"), log)
    if not entries:
        return {"ok": False, "error": "no .mdx/.md source files found under the project's sources"}

    out_dir = os.path.abspath(out_path or p.get("out_dir")
                              or os.path.join(HERE, "..", "Kotonoha-out", p.get("name") or p.get("id")))
    os.makedirs(out_dir, exist_ok=True)
    manifest = os.path.join(out_dir, "_sources.manifest.json")
    json.dump({"sources": entries}, open(manifest, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    combined = os.path.join(out_dir, "combined.mt-todo.json")
    engine = engine or os.path.join(HERE, "tm_match_analysis.py")
    template = template or os.path.join(HERE, "TM-Match-Explorer-demo.html")

    cmd = [sys.executable, engine, "--tmx", main_tm,
           "--source-manifest", manifest, "--template", template,
           "--out-dir", out_dir, "--combined-todo", combined]
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

    # Register each produced article; advance the definition's status + remember outputs.
    reg = 0
    if os.path.exists(combined):
        data = json.load(open(combined, encoding="utf-8-sig"))
        for art in data.get("articles", []):
            htmlp = art.get("html", "")
            if not htmlp:
                continue
            upsert(projects, htmlp, title=art.get("title"), source=art.get("source"),
                   segs=art.get("segs"), mt=art.get("mt"))
            reg += 1
    if p.get("status") in (None, "", "未解析"):
        p["status"] = "作業中"
    p["out_dir"] = out_dir; p["combined"] = combined
    p["last_run"] = now(); p["updated"] = now()
    save(store, projects)
    return {"ok": True, "out_dir": out_dir, "combined": combined,
            "registered": reg, "log": out_text}


def export_project(projects, store, pid, out_path="", cache_dir="",
                   mark_missing=False, log=print, capture=False):
    """Round-trip output: apply the definition's TM(s) to its sources and write a
    translated copy IN THE ORIGINAL FORMAT (via doc_export.py / doc_io). Run after
    pre-translation + MT + TEP writeback so the TM covers the content. Shared by the
    `export` CLI command and the serve API."""
    import subprocess
    p = find_by_id(projects, pid)
    if not p or p.get("type") != "project":
        return {"ok": False, "error": "project definition not found: %s" % pid}
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

    out_dir = os.path.abspath(out_path or p.get("out_dir")
                              or os.path.join(HERE, "..", "Kotonoha-out", p.get("name") or p.get("id")))
    os.makedirs(out_dir, exist_ok=True)
    manifest = os.path.join(out_dir, "_export.manifest.json")
    json.dump({"sources": entries}, open(manifest, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    exporter = os.path.join(HERE, "doc_export.py")
    cmd = [sys.executable, exporter, "--source-manifest", manifest,
           "--tmx", main_tm, "--out-dir", out_dir]
    subs = [st for st in p.get("sub_tms", []) if st]
    if subs:
        cmd += ["--sub-tmx"] + subs          # one flag, all paths (nargs="*")
    if cache_dir:
        cmd += ["--cache-dir", cache_dir]
    if mark_missing:
        cmd += ["--mark-missing"]

    log("プロジェクト「%s」: 元形式で翻訳版を出力 → %s"
        % (p.get("name", ""), os.path.join(out_dir, "translated")))
    out_text = ""
    if capture:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, encoding="utf-8", errors="replace")
        out_text = r.stdout or ""; rc = r.returncode
    else:
        rc = subprocess.call(cmd)
    if rc != 0:
        return {"ok": False, "error": "出力に失敗しました (exit %d)" % rc, "rc": rc, "log": out_text}
    return {"ok": True, "out_dir": os.path.join(out_dir, "translated"), "log": out_text}


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
    """MT を HTML に注入（inject_mt.py）。mode='single'（html+mt）/ 'batch'（combined-todo+combined-mt）。"""
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
        return {"ok": False, "error": "MT 注入に失敗しました (exit %d)" % rc, "rc": rc, "log": out}
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
            "segs": p.get("segs"), "mt": p.get("mt"), "memo": p.get("memo", ""),
            "due": p.get("due", ""), "updated": p.get("updated", ""),
            "source": src,
            "uri": (("/article?id=" + row_id(p)) if (served and p.get("html"))
                    else (file_uri(p.get("html", "")) if p.get("html") else "")),
            "id": row_id(p),
            "pid": (p.get("id", "") if is_def else ""),
            "cmd": (run_cmd(p.get("id", "")) if is_def else ""),
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
<title>Kotonoha プロジェクト一覧</title>
<style>
:root{--bg:#F5F6F8;--card:#fff;--ink:#1B1F27;--muted:#5C6470;--line:#E4E7EC;--accent:#146C82;
--work:#B77C1F;--work-bg:#F6ECD8;--rev:#146C82;--rev-bg:#E4F0F3;--done:#2E9E6B;--done-bg:#E4F3EC;}
@media(prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#101319;--card:#191D25;--ink:#E9EBEF;--muted:#9BA3AF;--line:#2A303A;--accent:#48AEC6;--work:#D6A24A;--work-bg:#33280f80;--rev:#48AEC6;--rev-bg:#17303880;--done:#4CB985;--done-bg:#15302480;}}
:root[data-theme=dark]{--bg:#101319;--card:#191D25;--ink:#E9EBEF;--muted:#9BA3AF;--line:#2A303A;--accent:#48AEC6;--work:#D6A24A;--work-bg:#33280f80;--rev:#48AEC6;--rev-bg:#17303880;--done:#4CB985;--done-bg:#15302480;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI","Noto Sans JP",system-ui,sans-serif;line-height:1.5}
.wrap{max-width:none;margin:0;padding:24px clamp(16px,2.5vw,48px) 60px}
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
#toast{position:fixed;left:50%;bottom:28px;transform:translateX(-50%) translateY(12px);background:var(--ink);color:var(--bg);padding:10px 16px;border-radius:10px;font-size:13px;max-width:min(92vw,640px);box-shadow:0 8px 24px rgba(0,0,0,.3);opacity:0;pointer-events:none;transition:opacity .18s,transform .18s;z-index:50}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.srvbadge{display:none;font-size:12px;font-weight:600;color:#fff;background:var(--done);border-radius:999px;padding:3px 10px;margin-left:10px;vertical-align:middle}
body.served .srvbadge{display:inline-block}
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
<h1>Kotonoha プロジェクト一覧<span class="srvbadge">サーバーモード（作成・実行が有効）</span></h1>
<div class="sub">記事行は「開く」で TEP 作業を<b>別タブ</b>で再開。定義行は「<b>実行</b>」で解析＋Pre-translation、「<b>出力</b>」で元形式の翻訳版を出力。各行の「<b>編集</b>」で状態・メモ・期日・削除。ツールバーの「<b>ツール ▾</b>」から MT注入・索引キャッシュ作成・TM書き戻し・UI Glossary を実行できます（<b>サーバーモード</b>時）。静的表示（file://）では「実行」はコマンドをコピーします。列ヘッダー右端をドラッグで<b>幅調整</b>、<b>列 ▾</b>で<b>表示/非表示</b>（ブラウザに保存）。</div>
<div class="tabs" id="tabs" hidden>
  <button class="tab" id="tab-projects" data-view="projects" aria-pressed="true" type="button">プロジェクト</button>
  <button class="tab" id="tab-terms" data-view="terms" aria-pressed="false" type="button">用語管理</button>
</div>
<div id="view-projects">
<div class="ctl">
  <button class="btn new" id="newbtn" type="button">＋ 新規作成</button>
  <input id="q" type="search" placeholder="タイトル・メモ・ソースを検索…">
  <button class="chip" data-st="all" aria-pressed="true">すべて</button>
  <button class="chip" data-st="作業中" aria-pressed="false">作業中</button>
  <button class="chip" data-st="レビュー中" aria-pressed="false">レビュー中</button>
  <button class="chip" data-st="完了" aria-pressed="false">完了</button>
  <label class="toggle"><input type="checkbox" id="hideDone"> 完了を隠す</label>
  <span class="colmenu" id="toolswrap" hidden><button class="btn" id="toolsbtn" type="button">ツール ▾</button><div id="toolspanel" class="toolspanel" hidden></div></span>
  <span class="colmenu"><button class="btn" id="colbtn" type="button">列 ▾</button><div id="colpanel" hidden></div></span>
  <button class="btn" id="resetbtn" type="button">既定に戻す</button>
  <button class="btn" id="lockbtn" type="button" aria-pressed="false">固定</button>
  <button class="themebtn" id="theme">◐ テーマ</button>
</div>
<div id="newnote" class="note" hidden>新規プロジェクトの作成・実行はランチャー <b>TM-Match-Explorer.bat</b> で行います：メニュー <b>[C]</b> プロジェクト作成＋実行（単一記事・フォルダーいずれも／メイン＋Product＋サブ TM）、または <b>[P]</b> 画面の <b>N=新規作成</b>・<b>G=保存した定義を実行</b>。作成・実行後にこのページを再読み込み（F5）すると一覧へ反映されます。<button class="btn" id="newclose" type="button" style="margin-left:8px">閉じる</button></div>
<div class="tablewrap"><table id="ptable"><colgroup id="cg"></colgroup>
<thead><tr id="thr"></tr></thead><tbody id="rows"></tbody></table></div>
<div class="empty" id="empty" hidden>該当するプロジェクトはありません。</div>
</div><!-- /view-projects -->
<div id="view-terms" hidden>
  <div class="ctl">
    <button class="btn new" id="termadd" type="button">＋ 用語を追加</button>
    <input id="tq" type="search" placeholder="用語を検索（ソース・ターゲット・ノート・ドキュメント）…">
    <button class="btn" id="termextract" type="button">用語を抽出…</button>
    <span class="colmenu"><button class="btn" id="termexportbtn" type="button">エクスポート ▾</button><div id="termexportpanel" class="toolspanel" hidden></div></span>
    <span class="termcount" id="termcount"></span>
  </div>
  <div class="tablewrap"><table id="ttable"><colgroup>
    <col style="width:200px"><col style="width:200px"><col style="width:260px"><col style="width:160px"><col style="width:150px"><col style="width:120px"><col style="width:128px"><col style="width:120px"></colgroup>
  <thead><tr><th>ソース</th><th>ターゲット</th><th>用例</th><th>ノート</th><th>ドキュメント</th><th>プロジェクト</th><th>更新</th><th class="act">操作</th></tr></thead>
  <tbody id="trows"></tbody></table></div>
  <div class="empty" id="tempty" hidden>用語がありません。「＋ 用語を追加」または「用語を抽出…」で登録してください。</div>
</div><!-- /view-terms -->
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
    if(p.uri){inner='<a class="open" href="'+esc(p.uri)+'" target="_blank" rel="noopener">開く</a>';}
    else if(p.pid){inner='<button class="run" type="button" data-pid="'+esc(p.pid)+'" data-cmd="'+esc(p.cmd)+'" data-n="'+p.n+'" title="'+(KT.served?'クリックで解析＋Pre-translation を実行':'クリックで実行コマンドをコピー ／ またはランチャー [P] で G → 番号 '+p.n)+'">実行</button>';
      if(KT.served){inner+='<button class="exp" type="button" data-pid="'+esc(p.pid)+'" title="TM を適用して元の形式で翻訳版を出力（解析→翻訳→TEP確定→書き戻しの後に実行）">出力</button>';}}
    if(KT.served&&p.id){inner+='<button class="edit" type="button" data-id="'+esc(p.id)+'" title="状態・メモ・期日・削除">編集</button>';}
    return "<tr>"+COLS.map(c=>cell(p,c.id)).join("")+'<td class="act">'+inner+'</td></tr>';
  }).join("");
}
// clipboard copy (file:// では navigator.clipboard が無い場合があるので execCommand に退避)
function fallbackCopy(t){try{const ta=document.createElement("textarea");ta.value=t;ta.style.position="fixed";ta.style.opacity="0";document.body.appendChild(ta);ta.focus();ta.select();const ok=document.execCommand("copy");document.body.removeChild(ta);return ok;}catch(e){return false;}}
function copyText(t){return (navigator.clipboard&&navigator.clipboard.writeText)?navigator.clipboard.writeText(t).then(()=>true,()=>fallbackCopy(t)):Promise.resolve(fallbackCopy(t));}
let toastT=null;
function toast(msg){let el=document.getElementById("toast");if(!el){el=document.createElement("div");el.id="toast";document.body.appendChild(el);}el.textContent=msg;el.classList.add("show");clearTimeout(toastT);toastT=setTimeout(()=>el.classList.remove("show"),3000);}
document.getElementById("rows").addEventListener("click",e=>{
  const eb=e.target.closest("button.edit");
  if(eb&&KT.served){const id=eb.getAttribute("data-id");const row=P.find(x=>x.id===id);if(row)openEdit(row);return;}
  const xb=e.target.closest("button.exp");
  if(xb&&KT.served){
    const pid=xb.getAttribute("data-pid");xb.disabled=true;const oldx=xb.textContent;xb.textContent="出力中…";
    api("/api/export",{method:"POST",body:JSON.stringify({id:pid})}).then(r=>{
      xb.disabled=false;xb.textContent=oldx;
      toast(r&&r.ok?("元形式で出力しました: "+(r.out_dir||"")):("出力失敗："+((r&&r.error)||"不明なエラー")));
    }).catch(err=>{xb.disabled=false;xb.textContent=oldx;toast("通信エラー: "+err);});
    return;
  }
  const b=e.target.closest("button.run");if(!b)return;
  const pid=b.getAttribute("data-pid"),cmd=b.getAttribute("data-cmd"),n=b.getAttribute("data-n");
  if(KT.served&&pid){
    b.disabled=true;const old=b.textContent;b.textContent="実行中…";
    api("/api/run",{method:"POST",body:JSON.stringify({id:pid})}).then(r=>{
      b.disabled=false;b.textContent=old;
      toast(r&&r.ok?("実行完了："+(r.registered||0)+" 記事を登録しました"):("実行失敗："+((r&&r.error)||"不明なエラー")));
      refresh();
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
  const st={name:"",sources:[],main_tm:"",product_tm:"",sub_tms:[]};
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
  bd.appendChild(pathField("メイン TM（.tmx・1つ・必須／マッチ用）","",()=>st.main_tm,x=>{st.main_tm=x;}));
  bd.appendChild(pathField("Product TM（.tmx・任意／用語集ヒント）","UI 用語の一致＋AI 翻訳の用語集ヒントに使います。",()=>st.product_tm,x=>{st.product_tm=x;}));
  // サブ TM（複数）
  const fsub=el("div","fld");fsub.appendChild(el("label",null,"サブ TM（.tmx・任意・複数可／マッチ用）"));const subList=el("div");fsub.appendChild(subList);const addSub=el("button","mini","＋ サブ TM 追加");fsub.appendChild(addSub);bd.appendChild(fsub);
  function drawSub(){subList.innerHTML="";if(!st.sub_tms.length){subList.appendChild(el("div","hint","（未追加）"));}st.sub_tms.forEach((t,i)=>{const r=el("div","srcitem");r.appendChild(el("span","p",t));const x=el("button","mini danger","削除");x.onclick=()=>{st.sub_tms.splice(i,1);drawSub();};r.appendChild(x);subList.appendChild(r);});}
  addSub.onclick=()=>pick("tmx",true).then(r=>{if(r&&r.available===false){openBrowser("tmx","",p=>{st.sub_tms.push(p);drawSub();});return;}(r&&r.paths||[]).forEach(p=>st.sub_tms.push(p));drawSub();}).catch(err=>toast("選択エラー: "+err));drawSub();
  m.appendChild(bd);
  // フッター
  const ft=el("div","ft");const run=el("button","primary","作成して実行");const mk=el("button","primary","作成のみ");const cancel=el("button","ghost","キャンセル");
  ft.appendChild(run);ft.appendChild(mk);ft.appendChild(cancel);m.appendChild(ft);cancel.onclick=closeOvl;
  function validate(){if(!st.name.trim()){toast("プロジェクト名を入力してください");return false;}if(!st.sources.length){toast("ソースを1つ以上追加してください");return false;}if(!st.main_tm){toast("メイン TM を選択してください");return false;}return true;}
  function create(then){if(!validate())return;run.disabled=true;mk.disabled=true;
    api("/api/create",{method:"POST",body:JSON.stringify(st)}).then(r=>{
      if(!r||!r.id){run.disabled=false;mk.disabled=false;toast("作成失敗："+((r&&r.error)||"不明"));return;}
      if(then==="run"){toast("作成しました。実行中…");api("/api/run",{method:"POST",body:JSON.stringify({id:r.id})}).then(rr=>{closeOvl();toast(rr&&rr.ok?("実行完了："+(rr.registered||0)+" 記事を登録しました"):("作成済／実行失敗："+((rr&&rr.error)||"不明")));refresh();}).catch(err=>{closeOvl();toast("作成済／実行の通信エラー: "+err);refresh();});}
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
  const sh=modalShell("MT を HTML に注入");
  sh.bd.appendChild(el("div","hint","翻訳済み mt-done は Claude 等で作成した成果物を指定します。単一＝1記事HTML＋mt-done、一括＝combined.mt-todo.json＋combined.mt-done.jsonl。"));
  const fm=el("div","fld");fm.appendChild(el("label",null,"モード"));const sel=el("select");[["single","単一（HTML＋mt-done）"],["batch","一括（combined）"]].forEach(o=>{const op=el("option",null,o[1]);op.value=o[0];sel.appendChild(op);});fm.appendChild(sel);sh.bd.appendChild(fm);
  const single=el("div");const batch=el("div");batch.hidden=true;
  single.appendChild(pathFieldK("HTML（生成済み）","",'html',()=>st.html,x=>{st.html=x;}));
  single.appendChild(pathFieldK("mt-done（.jsonl / .json）","",'json',()=>st.mt,x=>{st.mt=x;}));
  batch.appendChild(pathFieldK("combined.mt-todo.json","",'json',()=>st.combined_todo,x=>{st.combined_todo=x;}));
  batch.appendChild(pathFieldK("combined.mt-done.jsonl","",'json',()=>st.combined_mt,x=>{st.combined_mt=x;}));
  sh.bd.appendChild(single);sh.bd.appendChild(batch);
  sel.onchange=()=>{st.mode=sel.value;single.hidden=(st.mode!=="single");batch.hidden=(st.mode!=="batch");};
  const run=el("button","primary","注入");const cancel=el("button","ghost","キャンセル");cancel.onclick=closeOvl;
  run.onclick=()=>{busy(run,true,"注入中…");api("/api/inject",{method:"POST",body:JSON.stringify(st)}).then(r=>{busy(run,false);if(r&&r.ok){toast("注入しました");showLog("MT 注入結果",r.log);}else{toast("注入失敗："+((r&&r.error)||"不明"));if(r&&r.log)showLog("MT 注入ログ",r.log);}}).catch(err=>{busy(run,false);toast("通信エラー: "+err);});};
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
  sh.bd.appendChild(listFieldK("生成/TEP HTML（複数可）","",'html',st.html));
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
  [["MT を HTML に注入",openInject],["索引キャッシュを事前作成",openPrebuild],["TEP 結果を TM に書き戻す",openWriteback],["UI Glossary を作成",openGlossary],["ファイル比較 (EN)",openFileCompare],["JA バージョンチェック",openVersionCheck]].forEach(t=>{const b=el("button",null,t[0]);b.onclick=()=>{toolsPanel.hidden=true;t[1]();};toolsPanel.appendChild(b);});
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
  sh.bd.appendChild(listFieldK("生成/TEP HTML（複数可）","",'html',st.html));
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
  document.getElementById("tab-projects").setAttribute("aria-pressed",String(v==="projects"));
  document.getElementById("tab-terms").setAttribute("aria-pressed",String(v==="terms"));
  if(v==="terms")loadTerms();
}
document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click",()=>switchView(b.dataset.view)));

if(KT.served){document.body.classList.add("served");var _tw=document.getElementById("toolswrap");if(_tw)_tw.hidden=false;var _tabs=document.getElementById("tabs");if(_tabs)_tabs.hidden=false;refresh();}
</script></body></html>"""
    return (tpl.replace("__DATA__", data).replace("__COLS__", colmeta)
               .replace("__KTCFG__", ktcfg))

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
            so its term pane can call /api/* (file:// 配信では不可)。登録済み html に限定。"""
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

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            if u.path in ("/", "/index.html"):
                self._send(200, dashboard_html(load(STORE), served=True, token=TOKEN),
                           "text/html; charset=utf-8")
                return
            if u.path == "/article":
                q = urllib.parse.parse_qs(u.query)
                self._serve_article(q.get("id", [""])[0]); return
            if u.path.startswith("/api/"):
                if not self._auth():
                    self._send(403, {"error": "forbidden"}); return
                if u.path == "/api/projects":
                    self._send(200, {"rows": build_rows(load(STORE), served=True)}); return
                if u.path == "/api/browse":
                    q = urllib.parse.parse_qs(u.query)
                    self._send(200, list_dir(q.get("dir", [""])[0], q.get("kind", ["source"])[0])); return
                if u.path == "/api/terms":
                    q = urllib.parse.parse_qs(u.query)
                    seg = q.get("seg", [""])[0]
                    terms = load_terms(TERMSTORE)
                    self._send(200, {"rows": (terms_for_segment(terms, seg) if seg else terms)}); return
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
                                          sub_tms=payload.get("sub_tms", []))
                save(STORE, projs)
                self._send(200, {"id": pid}); return
            if u.path == "/api/run":
                projs = load(STORE)
                res = run_project(projs, STORE, payload.get("id", ""), engine=ENGINE,
                                  template=TEMPLATE, cache_dir=CACHE, log=lambda *x: None,
                                  capture=True)
                self._send(200, res); return
            if u.path == "/api/export":
                projs = load(STORE)
                res = export_project(projs, STORE, payload.get("id", ""), cache_dir=CACHE,
                                     mark_missing=bool(payload.get("mark_missing")),
                                     log=lambda *x: None, capture=True)
                self._send(200, res); return
            if u.path == "/api/set-status":
                projs = load(STORE)
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
                self._send(200, remove_project(projs, STORE, payload.get("id", ""),
                                               bool(payload.get("delete_file")))); return
            if u.path == "/api/inject":
                self._send(200, inject_mt_run(payload.get("mode", "single"),
                                              html=payload.get("html", ""), mt=payload.get("mt", ""),
                                              combined_todo=payload.get("combined_todo", ""),
                                              combined_mt=payload.get("combined_mt", ""), capture=True)); return
            if u.path == "/api/prebuild":
                self._send(200, prebuild_index(payload.get("univ", ""), prod=payload.get("prod", ""),
                                               cache_dir=payload.get("cache_dir", "") or CACHE,
                                               rebuild=bool(payload.get("rebuild")), capture=True)); return
            if u.path == "/api/writeback":
                self._send(200, writeback_run(xliff=payload.get("xliff", []),
                                              xliff_dir=payload.get("xliff_dir", ""),
                                              master=payload.get("master", ""),
                                              project_tmx=payload.get("project_tmx", ""),
                                              customer=payload.get("customer", ""),
                                              dry_run=bool(payload.get("dry_run", True)),
                                              backup=True, capture=True)); return
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
                self._send(200, {"ok": True, "term": rec}); return
            if u.path == "/api/term-delete":
                terms = load_terms(TERMSTORE)
                n = term_delete(terms, payload.get("id", ""))
                save_terms(TERMSTORE, terms)
                self._send(200, {"ok": True, "deleted": n}); return
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
