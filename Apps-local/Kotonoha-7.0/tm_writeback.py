# -*- coding: utf-8 -*-
"""TEP write-back: confirmed XLIFF segments -> Live_TM (Kotonoha beta2).

Reads XLIFF 1.2 exported by the TM Match Explorer browser UI and writes the
**confirmed** segments (the translator ticked 確定 / state="final" or note
"| confirmed") back into the working TMs under Live_TM:

  * Master TM   : Domo_Domo-Master.tmx  (all customers consolidated)
  * Project TM  : per --customer (University / Website / Marketing / Product / Subtitle)

Only confirmed segments with a non-empty target are written (per spec: nothing is
written back until the worker confirms). ICE context (x-previous/next-source-text)
is reconstructed from neighbouring trans-units so re-indexed Live_TM can judge ICE.

Existing Live_TM TMX files (written by this tool) are merged: a segment whose
source already exists is updated (newest target wins, changedate refreshed);
new sources are appended. If nothing is confirmed for a target TMX and that file
does not yet exist, it is not created.
"""
import argparse, re, sys, io, os, glob, html, time
import xml.etree.ElementTree as ET
import tm_writeback_lib  # 蓄積マージの中核（副作用なし・projects.py の TEP完了 と共通）

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

TM_ROOT = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working"
DEFAULT_LIVE = os.path.join(TM_ROOT, "Kotonoha", "Live_TM")

# customer -> project TMX filename (en_US -> ja_JP direction, undated canonical names)
CUSTOMER_TMX = {
    "university": "Domo_Domo University-en_US-ja_JP.tmx",
    "website":    "Domo_Domo Website-en_US-ja_JP.tmx",
    "marketing":  "Domo_Domo Marketing-en_US-ja_JP.tmx",
    "product":    "Domo_Domo Product-en_US-ja_JP.tmx",
    "subtitle":   "Domo_Domo Subtitle-en_US-ja_JP.tmx",
}

ap = argparse.ArgumentParser()
ap.add_argument("--xliff", nargs="*", default=[], help="one or more XLIFF files from the browser UI")
ap.add_argument("--xliff-dir", dest="xliff_dir", default="", help="folder of .xliff (recursive)")
ap.add_argument("--customer", default="", help="University / Website / Marketing / Product / Subtitle (routes the project TM). Omit to write Master only.")
ap.add_argument("--live-dir", dest="live_dir", default=DEFAULT_LIVE, help="Live_TM folder (default: %(default)s)")
ap.add_argument("--master", default="", help="Master TMX path (default: <live-dir>\\Domo_Domo-Master.tmx)")
ap.add_argument("--project-tmx", dest="project_tmx", default="", help="explicit project TMX path (overrides --customer mapping)")
ap.add_argument("--src-lang", dest="src_lang", default="en-US")
ap.add_argument("--tgt-lang", dest="tgt_lang", default="ja-JP")
ap.add_argument("--dry-run", dest="dry_run", action="store_true", help="report what would be written, change nothing")
args = ap.parse_args()

strip = lambda t: t.split("}")[-1]

# ---- collect XLIFF inputs ----
xfiles = list(args.xliff)
if args.xliff_dir:
    for pat in ("*.xliff", "*.xlf"):
        xfiles += glob.glob(os.path.join(args.xliff_dir, "**", pat), recursive=True)
seen = set(); xliffs = []
for p in xfiles:
    ap_ = os.path.abspath(p)
    if ap_ not in seen and os.path.isfile(p):
        seen.add(ap_); xliffs.append(p)
if not xliffs:
    print("ERROR: no XLIFF files (use --xliff ... or --xliff-dir ...)", flush=True); sys.exit(1)

def text_of(el):
    return "".join(el.itertext()) if el is not None else ""

def parse_xliff(path):
    """Return list of confirmed entries {src,tgt,prev,next} (in document order)."""
    tree = ET.parse(path); root = tree.getroot()
    tus = [el for el in root.iter() if strip(el.tag) == "trans-unit"]
    # ordered sources for context reconstruction
    srcs = []
    parsed = []
    for tu in tus:
        src = tgt = None; state = ""; note = ""
        for ch in tu.iter():
            ct = strip(ch.tag)
            if ct == "source" and src is None: src = text_of(ch)
            elif ct == "target" and tgt is None:
                tgt = text_of(ch); state = ch.attrib.get("state", "")
            elif ct == "note" and not note: note = text_of(ch)
        src = (src or "").strip(); tgt = (tgt or "").strip()
        confirmed = (state == "final") or ("confirmed" in note.lower())
        parsed.append({"src": src, "tgt": tgt, "confirmed": confirmed})
        srcs.append(src)
    out = []
    for i, e in enumerate(parsed):
        if not e["confirmed"] or not e["src"] or not e["tgt"]:
            continue
        prev = srcs[i-1] if i > 0 else ""
        nxt = srcs[i+1] if i+1 < len(srcs) else ""
        out.append({"src": e["src"], "tgt": e["tgt"], "prev": prev, "next": nxt})
    return out, len(tus)

# ---- read confirmed entries from all XLIFFs ----
entries = []
for xp in xliffs:
    ents, ntu = parse_xliff(xp)
    print("xliff: %-50s trans-units %4d | confirmed %4d" % (os.path.basename(xp)[:50], ntu, len(ents)), flush=True)
    entries.extend(ents)
print("total confirmed segments:", len(entries), flush=True)
if not entries:
    print("nothing confirmed -> nothing to write. (作業者が確定するまで書き戻しません)", flush=True)
    sys.exit(0)

# ---- TMX read / merge / write （中核は tm_writeback_lib に集約。CLI 出力は従来どおり） ----
def load_tmx(path):
    return tm_writeback_lib.load_tmx(path, args.src_lang, args.tgt_lang)

def xesc(s):
    return html.escape(s or "", quote=False)

def write_tmx(path, od):
    return tm_writeback_lib.write_tmx(path, od, args.src_lang, args.tgt_lang)

def merge_into(path, entries, label):
    r = tm_writeback_lib.merge_entries(path, entries, args.src_lang, args.tgt_lang,
                                       dry_run=args.dry_run)
    print("  %-9s %-34s TUs %d -> %d (new %d, same %d)"
          % (label, os.path.basename(path), r["before"], r["after"],
             r["added"], r["refreshed"]), flush=True)
    return r["added"], r["refreshed"]

# ---- targets: Master (always) + project (by customer) ----
master = args.master or os.path.join(args.live_dir, "Domo_Domo-Master.tmx")
print("\n== write-back%s ==" % (" (DRY RUN)" if args.dry_run else ""), flush=True)
merge_into(master, entries, "Master")

proj_path = ""
if args.project_tmx:
    proj_path = args.project_tmx
elif args.customer:
    key = args.customer.strip().lower()
    if key in CUSTOMER_TMX:
        proj_path = os.path.join(args.live_dir, CUSTOMER_TMX[key])
    else:
        print("  WARNING: unknown --customer '%s' (expected one of: %s). Skipping project TM."
              % (args.customer, ", ".join(sorted(CUSTOMER_TMX))), flush=True)
else:
    print("  (no --customer / --project-tmx given -> Master only)", flush=True)

if proj_path:
    merge_into(proj_path, entries, "Project")

print("\nDONE.%s" % (" (dry run: no files changed)" if args.dry_run else ""), flush=True)
