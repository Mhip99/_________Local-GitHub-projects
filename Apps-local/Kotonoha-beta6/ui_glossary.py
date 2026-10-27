# -*- coding: utf-8 -*-
"""UI Glossary builder (Kotonoha beta6).

Extracts UI terms -- UI elements, commands, and messages -- from the *work*
(source .mdx, a produced/TEP HTML, and/or a confirmed XLIFF) and writes a
bilingual glossary (CSV + JSON). Japanese is filled, in priority order, from:
  1. the confirmed translation of a whole short segment (highest confidence),
  2. an exact match in the Product / University TM index (reuses tm_index cache),
  3. verbatim (commands / product names that stay in English),
  4. blank -- left for the translator to fill.

Sources of UI terms:
  * source .mdx  -> inline markup: **bold** (UI elements/labels), `code`
                    (commands / UI values), and menu paths "A > B".
  * HTML / XLIFF -> short whole segments that look like UI labels or messages.

Usage (any combination; at least one source required):
  python ui_glossary.py --source ART.mdx --product-tmx PROD.tmx --cache-dir IDX --out gloss
  python ui_glossary.py --html TM-Match-Explorer-ART.html --out gloss
  python ui_glossary.py --xliff ART.xliff --confirmed-only --out gloss
"""
import argparse, re, sys, io, os, json, csv, glob, html as _html
import xml.etree.ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# tm_index is optional (only needed for TM-based JA lookup)
try:
    import tm_index
    from tm_index import norm as _norm
    HAVE_TMINDEX = True
except Exception:
    HAVE_TMINDEX = False
    _XTAG = re.compile(r"<[^>]+>")
    def _norm(s):
        s = _XTAG.sub(" ", s or "")
        s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
        s = re.sub(r"[*_`#>|~]", " ", s)
        return re.sub(r"\s+", " ", s).strip().lower()

TM_ROOT = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working"
DEFAULT_CACHE = os.path.join(TM_ROOT, "Kotonoha", "Index")

ap = argparse.ArgumentParser()
ap.add_argument("--source", nargs="*", default=[], help="source .mdx (inline UI markup)")
ap.add_argument("--source-dir", dest="source_dir", default="", help="folder of .mdx (recursive)")
ap.add_argument("--html", nargs="*", default=[], help="produced/TEP HTML (const SEG) for EN->JA segments")
ap.add_argument("--xliff", nargs="*", default=[], help="XLIFF for EN->JA segments")
ap.add_argument("--xliff-dir", dest="xliff_dir", default="", help="folder of .xliff (recursive)")
ap.add_argument("--confirmed-only", dest="confirmed_only", action="store_true",
                help="XLIFF: use only confirmed (state=final / note 'confirmed') segments")
ap.add_argument("--tmx", default="", help="University TM (optional, for JA lookup)")
ap.add_argument("--product-tmx", dest="product_tmx", default="", help="Product TM (optional, for JA lookup)")
ap.add_argument("--cache-dir", dest="cache_dir", default=DEFAULT_CACHE, help="index cache folder")
ap.add_argument("--max-words", dest="max_words", type=int, default=6, help="max words for a UI label/term")
ap.add_argument("--out", required=True, help="output path prefix (writes <out>.csv and <out>.json)")
args = ap.parse_args()

MAXW = args.max_words

# ---------- optional TM index for JA lookup ----------
exact_target = {}     # norm_en -> ja (any TM)
product_terms = {}    # norm_en -> {"en","ja"} (short Product terms)
if (args.tmx or args.product_tmx):
    if not HAVE_TMINDEX:
        print("WARNING: tm_index not importable; skipping TM-based JA lookup", flush=True)
    else:
        specs = []
        if args.tmx: specs.append((args.tmx, False))
        if args.product_tmx: specs.append((args.product_tmx, True))
        idx = tm_index.load_or_build(specs, args.cache_dir, log=lambda *a: print(*a, flush=True))
        exact_target = idx.exact_target
        product_terms = idx.product_terms
        print("JA lookup ready: exact keys %d | product terms %d" % (len(exact_target), len(product_terms)), flush=True)

def lookup_ja(en):
    """Return (ja, source) using the TM index; ('', '') if none."""
    k = _norm(en)
    if k in product_terms:
        return product_terms[k]["ja"], "product-tm"
    if k in exact_target:
        return exact_target[k], "tm"
    return "", ""

ASCII_CMD = re.compile(r"^[\x20-\x7E]+$")
def is_commandish(en):
    """ASCII-only token that typically stays in English (command / product / value)."""
    return bool(ASCII_CMD.match(en)) and not re.search(r"[.!?]$", en)

# ---------- glossary accumulator ----------
# key = norm_en -> entry
GLOSS = {}
TYPE_RANK = {"segment": 0, "ui-bold": 1, "ui-code": 2, "menu-path": 3, "label": 4, "message": 5}

def add_term(en, ja, typ, ja_src, count=1):
    en = (en or "").strip()
    if not en:
        return
    k = _norm(en)
    if not k or len(k) < 2:
        return
    e = GLOSS.get(k)
    if e is None:
        GLOSS[k] = {"en": en, "ja": ja or "", "type": typ, "ja_src": ja_src, "count": count}
        return
    e["count"] += count
    # prefer a real JA over blank; prefer higher-confidence type (lower rank)
    if not e["ja"] and ja:
        e["ja"] = ja; e["ja_src"] = ja_src
    if TYPE_RANK.get(typ, 9) < TYPE_RANK.get(e["type"], 9):
        e["type"] = typ
        if ja and typ == "segment":
            e["ja"] = ja; e["ja_src"] = ja_src

# ---------- 1) inline UI markup from source .mdx ----------
RE_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*|__([^_\n]+?)__")
RE_CODE = re.compile(r"`([^`\n]+?)`")
RE_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")

def clean_token(t):
    t = RE_LINK.sub(r"\1", t)
    t = t.replace("**", "").replace("`", "").strip()
    t = re.sub(r"\s+", " ", t)
    return t.strip(" :：.,、。")

def wc(s):
    return len(s.split())

def harvest_source(path):
    raw = open(path, encoding="utf-8-sig").read()
    # drop code fences and frontmatter/import lines (not UI prose)
    body = re.sub(r"(?s)```.*?```", " ", raw)
    body = re.sub(r"(?s)^\s*---\s*\n.*?\n---\s*\n", "", body, count=1)
    body = re.sub(r"(?m)^\s*(?:import|export)\s.*$", " ", body)
    for m in RE_BOLD.finditer(body):
        tok = clean_token(m.group(1) or m.group(2) or "")
        if not tok or wc(tok) > MAXW:
            continue
        if ">" in tok and wc(tok) <= MAXW + 2:
            ja, src = lookup_ja(tok)
            add_term(tok, ja, "menu-path", src)
        else:
            ja, src = lookup_ja(tok)
            if not ja and is_commandish(tok):
                ja, src = tok, "verbatim"
            add_term(tok, ja, "ui-bold", src)
    for m in RE_CODE.finditer(body):
        tok = clean_token(m.group(1))
        if not tok or wc(tok) > MAXW:
            continue
        ja, src = lookup_ja(tok)
        if not ja and is_commandish(tok):
            ja, src = tok, "verbatim"
        add_term(tok, ja, "ui-code", src)

# ---------- 2) short segments from HTML (const SEG) ----------
def _plain(parts):
    try:
        return "".join(p[1] for p in parts if p and p[0] != "del")
    except Exception:
        return ""

STOP1 = frozenset("""a an the this that and or but of to in on at by for with from as is are was were be
if then so no yes you your we our they it its not do does did will can may""".split())

def _strip_tags(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()

def classify_segment(en):
    """Return (type, cleaned_en): 'label'/'message'/None. Rejects noisy/code segments."""
    en = _strip_tags(en)
    if not en:
        return None, en
    n = wc(en)
    if n == 0 or n > MAXW:
        return None, en
    if re.search(r"[`|{}<>]", en):        # code / value lists / leftover tags -> not a clean UI term
        return None, en
    # message: a short, self-contained sentence
    if re.match(r"^[A-Z].*[.!?]$", en) and n >= 4:
        return "message", en
    # label: clean token(s), each word Title-cased, no punctuation
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9 /&_+-]*$", en):
        words = re.findall(r"[A-Za-z][A-Za-z0-9'+/-]*", en)
        if not words:
            return None, en
        caps = sum(1 for w in words if w[:1].isupper())
        if caps >= max(1, len(words) - 1):
            if n == 1 and (en.lower() in STOP1 or len(en) < 3):
                return None, en
            return "label", en
    return None, en

def harvest_html(path):
    txt = open(path, encoding="utf-8").read()
    m = re.search(r"const SEG = (\[[\s\S]*?\]);\s*\nconst BANDS", txt)
    if not m:
        print("  (no const SEG in %s)" % os.path.basename(path), flush=True)
        return
    seg = json.loads(m.group(1))
    for s in seg:
        en = _plain(s.get("en", []))
        ja = _strip_tags(_plain(s.get("ja", [])))
        typ, en = classify_segment(en)
        if typ and ja:
            add_term(en, ja, typ, "work")

# ---------- 3) short segments from XLIFF ----------
def _text(el):
    return "".join(el.itertext()) if el is not None else ""

def harvest_xliff(path, confirmed_only):
    strip = lambda t: t.split("}")[-1]
    root = ET.parse(path).getroot()
    for tu in root.iter():
        if strip(tu.tag) != "trans-unit":
            continue
        src = tgt = None; state = ""; note = ""
        for ch in tu.iter():
            ct = strip(ch.tag)
            if ct == "source" and src is None: src = _text(ch)
            elif ct == "target" and tgt is None:
                tgt = _text(ch); state = ch.attrib.get("state", "")
            elif ct == "note" and not note: note = _text(ch)
        src = (src or "").strip(); tgt = _strip_tags(tgt or "")
        confirmed = (state == "final") or ("confirmed" in note.lower())
        if confirmed_only and not confirmed:
            continue
        typ, src = classify_segment(src)
        if typ and tgt:
            add_term(src, tgt, typ, "work")

# ---------- collect inputs ----------
sources = list(args.source)
if args.source_dir:
    for pat in ("*.mdx", "*.md"):
        sources += glob.glob(os.path.join(args.source_dir, "**", pat), recursive=True)
xliffs = list(args.xliff)
if args.xliff_dir:
    for pat in ("*.xliff", "*.xlf"):
        xliffs += glob.glob(os.path.join(args.xliff_dir, "**", pat), recursive=True)

if not (sources or args.html or xliffs):
    print("ERROR: give at least one of --source / --source-dir / --html / --xliff / --xliff-dir", flush=True)
    sys.exit(1)

for p in sources:
    if os.path.isfile(p):
        print("source:", os.path.basename(p), flush=True); harvest_source(p)
for p in args.html:
    if os.path.isfile(p):
        print("html:", os.path.basename(p), flush=True); harvest_html(p)
for p in xliffs:
    if os.path.isfile(p):
        print("xliff:", os.path.basename(p), flush=True); harvest_xliff(p, args.confirmed_only)

# ---------- output ----------
rows = sorted(GLOSS.values(),
              key=lambda e: (TYPE_RANK.get(e["type"], 9), -e["count"], e["en"].lower()))
n_ja = sum(1 for e in rows if e["ja"])
print("\nUI glossary: %d terms | with JA %d | need JA %d" % (len(rows), n_ja, len(rows) - n_ja), flush=True)

csv_path = args.out + ".csv"
# UTF-8 with BOM so Excel shows Japanese correctly
with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["EN", "JA", "Type", "JA_source", "Count"])
    for e in rows:
        w.writerow([e["en"], e["ja"], e["type"], e["ja_src"], e["count"]])
json_path = args.out + ".json"
json.dump({"count": len(rows), "with_ja": n_ja, "terms": rows},
          open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print("saved:", csv_path, flush=True)
print("saved:", json_path, flush=True)
