# -*- coding: utf-8 -*-
"""TM Match Analysis + Pre-translation engine (Kotonoha beta2).

Adds to beta1:
  (1) TMX index caching   -- via tm_index.load_or_build (pickle, fingerprinted).
  (2) Batch               -- --source may be repeated, or --source-dir globs *.mdx;
                             the index is built/loaded ONCE and reused for all articles.
  (3) Combined MT to-do   -- --combined-todo merges every article's <=74% segments into
                             one file (with global ids) so MT can be done in one pass;
                             inject_mt.py --combined-* fans the results back per article.

EN source x TMX(s) -> ICE/100%/fuzzy bands; pre-translation fills TM targets for >=75%
and flags <=74% for MT (AI translation). Emits a self-contained HTML viewer per article
plus per-article mt-todo.json (beta1-compatible) and, optionally, one combined to-do.
"""
import argparse, re, sys, io, os, json, html, difflib, glob, time
from collections import Counter

import tm_index
from tm_index import norm, h, XTAG
try:
    import json_io          # Domo アプリ コンテンツ JSON の抽出（.json ソース用）
except Exception:
    json_io = None

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ---- default TM locations (per TM management spec) ----
TM_ROOT = r"C:\Users\Masaaki.Hori\OneDrive - Domo Inc\________GitHub-production\TM manaegment\TM\___Working"
DEFAULT_CACHE = os.path.join(TM_ROOT, "Kotonoha", "Index")

ap = argparse.ArgumentParser()
ap.add_argument("--source", nargs="*", default=[], help="one or more EN source .mdx (batch)")
ap.add_argument("--source-dir", dest="source_dir", default="", help="folder of .mdx (recursive) -- batch")
ap.add_argument("--source-manifest", dest="source_manifest", default="",
                help='JSON {"sources":[{"src":<abs .mdx>,"rel":<output stem, / = subdir>}]} '
                     "-- batch with folder-hierarchy-preserving output (used by projects.py run)")
ap.add_argument("--tmx", required=True, help="primary / main TM (match source)")
ap.add_argument("--sub-tmx", dest="sub_tmx", nargs="*", default=[],
                help="additional match TM(s), treated like --tmx (exact/fuzzy matches)")
ap.add_argument("--product-tmx", dest="product_tmx", default="",
                help="Product TM: extra UI matches + MT glossary hints")
ap.add_argument("--template", required=True)
ap.add_argument("--out", default="", help="output HTML (single-source mode)")
ap.add_argument("--out-dir", dest="out_dir", default="", help="output folder (batch mode)")
ap.add_argument("--title", default="", help="article title (single-source only; batch derives per file)")
ap.add_argument("--project-name", dest="project_name", default="", help="サマリーのメタ情報に表示するプロジェクト名（projects.py が渡す）")
ap.add_argument("--project-detail", dest="project_detail", default="", help="サマリーのメタ情報に表示するプロジェクト詳細")
ap.add_argument("--run-mt", dest="run_mt", default="1",
                help="1: MT(≤74%)を翻訳欄に反映する前提 / 0: MTは履歴ペインに表示し翻訳欄は英語のまま（META.runMT に記録）")
ap.add_argument("--use-notapproved", dest="use_notapproved", default="1",
                help="1: 未承認(notapproved)のTUもPre-translation候補に使う / 0: approvedのみ使う（notapprovedを索引から除外）")
ap.add_argument("--cache-dir", dest="cache_dir", default=DEFAULT_CACHE,
                help="index cache folder (default: %(default)s)")
ap.add_argument("--no-cache", dest="no_cache", action="store_true", help="do not read/write the index cache")
ap.add_argument("--rebuild-cache", dest="rebuild_cache", action="store_true", help="force rebuild the index cache")
ap.add_argument("--combined-todo", dest="combined_todo", default="",
                help="write one merged mt-todo (global ids) across all articles for a single MT pass")
args = ap.parse_args()

# ---- collect sources ----
# rel_of maps a source's abspath to its intended output stem (manifest mode only),
# where "/" separators become sub-folders under --out-dir (folder hierarchy preserved).
rel_of = {}
if args.source_manifest:
    man = json.load(open(args.source_manifest, encoding="utf-8-sig"))
    entries = man.get("sources", man) if isinstance(man, dict) else man
    sources = []
    for e in entries:
        sp = e.get("src", "") if isinstance(e, dict) else e
        if sp:
            sources.append(sp)
            if isinstance(e, dict) and e.get("rel"):
                rel_of[os.path.abspath(sp)] = e["rel"]
else:
    sources = list(args.source)
    if args.source_dir:
        for pat in ("*.mdx", "*.md"):
            sources += glob.glob(os.path.join(args.source_dir, "**", pat), recursive=True)
# de-dup, keep order, normalize
seen = set(); srcs = []
for p in sources:
    ap_ = os.path.abspath(p)
    if ap_ not in seen and os.path.isfile(p):
        seen.add(ap_); srcs.append(p)
if not srcs:
    print("ERROR: no source files (use --source ..., --source-dir ..., or --source-manifest ...)", flush=True); sys.exit(1)

batch = len(srcs) > 1 or bool(args.source_dir) or bool(args.source_manifest)
if batch and not args.out_dir:
    print("ERROR: batch mode needs --out-dir", flush=True); sys.exit(1)
if not batch and not args.out and not args.out_dir:
    print("ERROR: single-source mode needs --out (or --out-dir)", flush=True); sys.exit(1)
if args.out_dir:
    os.makedirs(args.out_dir, exist_ok=True)
print("sources: %d | batch=%s" % (len(srcs), batch), flush=True)

# ---- build / load index (feature 1) ----
# primary + any sub TM(s) are match sources (is_product=False); product TM is special
# (UI term matches + glossary hints). The index cache keys on the full spec set.
specs = [(args.tmx, False)]
for s in (args.sub_tmx or []):
    if s:
        specs.append((s, False))
if args.product_tmx:
    specs.append((args.product_tmx, True))
_USE_UNAPP = str(args.use_notapproved).strip() not in ("0", "false", "False", "")
idx = tm_index.load_or_build(specs, args.cache_dir,
                             no_cache=args.no_cache, rebuild=args.rebuild_cache,
                             use_notapproved=_USE_UNAPP,
                             log=lambda *a: print(*a, flush=True))
exact_target = idx.exact_target; ice_ctx = idx.ice_ctx
inv = idx.inv; keys = idx.keys; product_terms = idx.product_terms
exact_hist = getattr(idx, "exact_hist", {})   # norm_src -> [{"ja","date"},...] 版履歴（履歴ペイン用）
src_tm = getattr(idx, "src_tm", {})           # norm_src -> 由来TMX絶対パス（TEP完了の書き戻しルーティング用）
src_status = getattr(idx, "src_status", {})   # norm_src -> 採用訳の x-xtm-status（approved/notapproved/""）

def hist_of(k):
    """Return this source's past translations, newest first, for the editor history pane.
    タグは {n} トークンへ正規化して返す（<x id="xN"/> を履歴に生表示しない）。"""
    lst = exact_hist.get(k) or []
    lst = sorted(lst, key=lambda r: (r.get("date") or ""), reverse=True)
    return [dict(r, ja=norm_tm_tags(r.get("ja", ""))) for r in lst]

# ---- Product glossary lookup (phrase match by first token) ----
pterm_by_first = {}
for k, v in product_terms.items():
    toks = tuple(k.split())
    pterm_by_first.setdefault(toks[0], []).append((toks, v["en"], v["ja"]))
for lst in pterm_by_first.values():
    lst.sort(key=lambda x: -len(x[0]))

def glossary_hits(sn, cap=12):
    toks = sn.split(); n = len(toks); hits = []; seen = set(); i = 0
    while i < n:
        cands = pterm_by_first.get(toks[i]); matched = False
        if cands:
            for tt, en, ja in cands:
                L = len(tt)
                if i + L <= n and tuple(toks[i:i+L]) == tt:
                    key = (en, ja)
                    if key not in seen:
                        seen.add(key); hits.append({"en": en, "ja": ja})
                    i += L; matched = True; break
        if not matched:
            i += 1
        if len(hits) >= cap:
            break
    return hits

# ---- segmentation (beta1 logic + JSX title="" extraction) ----
# JSX component headings carry translatable text in a title attribute, e.g.
#   <Accordion title="When will my users start seeing these messages?">
# These must become their own segments. We harvest title="..."/'...' per line (in
# document order) BEFORE stripping tags, otherwise a one-sentence title is swallowed
# whole as a <...> tag and a multi-sentence title splits mid-attribute into garbage
# like `<Accordion title="...` / `What happened?">`.
TITLE_ATTR = re.compile(r'\btitle\s*=\s*"([^"]*)"' + r"|\btitle\s*=\s*'([^']*)'")

def read_segments(path):
    raw = open(path, encoding="utf-8-sig").read()
    m = re.search(r"(?s)^\s*---\s*\n(.*?)\n---\s*\n?", raw)
    title = None; body = raw
    if m:
        fm = m.group(1); body = raw[m.end():]
        tm = re.search(r"(?mi)^\s*title\s*:\s*(.+?)\s*$", fm)
        if tm: title = tm.group(1).strip().strip('"\'')
    body = re.sub(r"(?s)```.*?```", " ", body)
    body = re.sub(r"(?s)~~~.*?~~~", " ", body)
    body = re.sub(r"(?m)^\s*(?:import|export)\s.*$", " ", body)
    segs = []
    if title: segs.append(title)

    def emit(text):
        for sent in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s+", text):
            sent = re.sub(r"\s+", " ", sent).strip()
            if sent and norm(sent): segs.append(sent)

    for line in body.split("\n"):
        # 1) harvest JSX title attribute(s) as their own sentence(s), in order
        titles = [a or b for (a, b) in TITLE_ATTR.findall(line)]
        # 2) remove all JSX/HTML tags so no markup (and no already-harvested title)
        #    leaks into a body segment
        stripped = re.sub(r"<[^>]+>", " ", line)
        l = re.sub(r"^\s*([-*+]|\d+\.|#{1,6}|>)\s*", "", stripped).strip()
        for t in titles:
            emit(t)
        if not l: continue
        if re.match(r"^\|?[\s:\-|]+\|?$", l): continue
        l = l.replace("|", " ").strip()
        emit(l)
    return segs, title

# ---- matching (identical logic to beta1) ----
def band_of(r):
    if r >= 1.0: return "100%"
    if r >= 0.95: return "95-99%"
    if r >= 0.85: return "85-94%"
    if r >= 0.75: return "75-84%"
    return "<=74%"
CAT = {"ICE":"Reused","100%":"Reused","95-99%":"Modified","85-94%":"Modified","75-84%":"Modified","<=74%":"Added"}

def best_fuzzy(qn):
    qtok = qn.split()
    if not qtok: return None, 0.0
    toks = sorted(set(qtok), key=lambda t: len(inv.get(t, [])))
    cand = []; seen = set()
    for t in toks[:6]:
        for kid in inv.get(t, []):
            if kid not in seen:
                seen.add(kid); cand.append(kid)
        if len(cand) > 400: break
    best = None; bestr = 0.0
    sm = difflib.SequenceMatcher(); sm.set_seq2(qtok)
    for kid in cand:
        k = keys[kid]; sm.set_seq1(k.split())
        r = sm.ratio()
        if r > bestr: bestr = r; best = k
    return best, bestr


def topk_fuzzy(qn, k=50):
    """近い TM エントリを類似度の高い順に最大 k 件返す（履歴ペインの候補表示用）。
    各要素 = {"ja": 正規化済み訳文, "pct": 類似度%}。訳文が同一のものは上位のみ残す。"""
    qtok = qn.split()
    if not qtok:
        return []
    toks = sorted(set(qtok), key=lambda t: len(inv.get(t, [])))
    cand = []; seen = set()
    for t in toks[:6]:
        for kid in inv.get(t, []):
            if kid not in seen:
                seen.add(kid); cand.append(kid)
        if len(cand) > 400:
            break
    sm = difflib.SequenceMatcher(); sm.set_seq2(qtok)
    scored = []
    for kid in cand:
        kk = keys[kid]; sm.set_seq1(kk.split())
        scored.append((kk, sm.ratio()))
    scored.sort(key=lambda x: x[1], reverse=True)
    out = []; seen_ja = set()
    for kk, r in scored:
        tgt = exact_target.get(kk, "")
        if not tgt:
            continue
        nt = norm_tm_tags(tgt)
        if nt in seen_ja:
            continue
        seen_ja.add(nt)
        out.append({"ja": nt, "en": kk, "pct": round(r * 100, 1)})
        if len(out) >= k:
            break
    return out

def tok_diff(a, b):
    at = a.split(); bt = b.split(); out = []
    for op,i1,i2,j1,j2 in difflib.SequenceMatcher(None, at, bt).get_opcodes():
        if op == "equal": out.append(["eq", " ".join(bt[j1:j2])+" "])
        else:
            if i1<i2: out.append(["del", " ".join(at[i1:i2])+" "])
            if j1<j2: out.append(["add", " ".join(bt[j1:j2])+" "])
    return out or [["eq", b]]

_TM_X_RE = re.compile(r'<x\b[^>]*?/?>', re.I)
_TM_ID_RE = re.compile(r'\bid\s*=\s*"([^"]*)"', re.I)
def norm_tm_tags(tgt):
    """TM(TMX)ターゲットのXLIFFインラインタグ <x id="xN"/> をツールの {N} トークンへ正規化。
    ソースは json_io で {n} トークン化されるのに対し、TMターゲットは TMX 由来の <x .../> のまま
    格納されているため、そのままだとチップ表示が崩れる（例: ja に「<x id="x1"/>…」が生で残る）。
    id の数字を取り出して {N} に、数字が無ければ出現順に採番する。<x .../> 以外は変更しない。"""
    if not tgt or "<x" not in tgt.lower():
        return tgt
    seq = [0]
    def repl(m):
        mid = _TM_ID_RE.search(m.group(0))
        dig = re.sub(r"\D", "", mid.group(1)) if mid else ""
        if dig:
            return "{%d}" % int(dig)
        seq[0] += 1
        return "{%d}" % seq[0]
    return _TM_X_RE.sub(repl, tgt)

def append_missing_tags(src, tgt):
    """ソース src の {n} タグのうち tgt に含まれないものを末尾に補う（タグ落ち防止）。
    TM訳にソースのタグが無いと編集欄にチップ（タグアイコン）が出ないため、全ソースタグを
    必ず訳文に存在させる。順序維持・重複排除。"""
    seen = set(); add = ""
    for m in re.finditer(r"\{\d+\}", src or ""):
        tg = m.group(0)
        if tg in seen:
            continue
        seen.add(tg)
        if tg not in (tgt or ""):
            add += tg
    return (tgt or "") + add

def analyze(src):
    """src: list of source sentences -> (rows, mt_todo)."""
    src_norm = [norm(s) for s in src]
    rows = []; mt_todo = []
    for i, s in enumerate(src):
        sn = src_norm[i]
        if sn in exact_target:
            tgt = append_missing_tags(s, norm_tm_tags(exact_target[sn]))
            ph = h(norm(src[i-1])) if i>0 else h("")
            nh = h(norm(src[i+1])) if i+1<len(src) else h("")
            is_ice = (sn in ice_ctx) and ((ph,nh) in ice_ctx[sn])
            band = "ICE" if is_ice else "100%"
            rows.append({"b":band,"cat":CAT[band],"pct":"100.0","st":"tm",
                         "en":[["eq", s]],"tm":tgt,"ja":[["eq", tgt]],"hist":hist_of(sn),
                         "glossary":glossary_hits(sn),"srctm":src_tm.get(sn,""),"status":src_status.get(sn,"")})
        else:
            bestk, r = best_fuzzy(sn)
            band = band_of(r); pct = "%.1f" % (r*100)
            if bestk and r >= 0.75:
                tgt = append_missing_tags(s, norm_tm_tags(exact_target.get(bestk, "")))
                rows.append({"b":band,"cat":CAT[band],"pct":pct,"st":"tm",
                             "en":tok_diff(bestk, s),"tm":tgt,"ja":[["eq", tgt]],"hist":hist_of(bestk),
                             "glossary":glossary_hits(sn),"srctm":src_tm.get(bestk,""),"status":src_status.get(bestk,"")})
            else:
                # \u30de\u30c3\u30c1\u7387 \u226474% \u3067\u3082\u3001TM \u306b\u65e2\u8a33\u304c\u3042\u308c\u3070\u985e\u4f3c\u5ea6\u306e\u9ad8\u3044\u9806\u306b\u5019\u88dc\u3092\u5c65\u6b74\u3078\uff08\u4e0a\u4f4d\u306f UI \u304c5\u4ef6\u305a\u3064\u8868\u793a\uff09\u3002
                bh = topk_fuzzy(sn, 50)
                rows.append({"b":"<=74%","cat":"Added","pct":pct if bestk else "0.0","st":"mt",
                             "en":[["add", s]],"tm":"\u2014","ja":[],"hist":bh,
                             "glossary":glossary_hits(sn),"srctm":"","status":""})
                # MT \u3092\u5916\u90e8AI\u3067\u4f5c\u308b\u969b\u3001\u6307\u5b9aTM\u306e\u8a72\u5f53\u65e2\u8a33\uff08\u6700\u3082\u8fd1\u3044\u5019\u88dc\u30fb\u4e0a\u4f4d5\u4ef6\uff09\u3092\u5fc5\u305a\u53c2\u7167\u3067\u304d\u308b\u3088\u3046\u540c\u68b1\u3059\u308b
                mt_todo.append({"i":i, "en":s, "pct":float(pct if bestk else 0.0),
                                "glossary":glossary_hits(sn), "tm_candidates":bh[:5]})
    return rows, mt_todo

# ---- template (read once) ----
tpl_src = open(args.template, encoding="utf-8").read()
def tm_list():
    """使用TMの一覧（メイン/サブ/Product）をメタ情報用に組み立てる。"""
    lst = []
    if args.tmx:
        lst.append({"role": "メインTM", "name": os.path.basename(args.tmx), "path": os.path.abspath(args.tmx)})
    for st in (args.sub_tmx or []):
        if st:
            lst.append({"role": "サブTM", "name": os.path.basename(st), "path": os.path.abspath(st)})
    if args.product_tmx:
        lst.append({"role": "Product TM", "name": os.path.basename(args.product_tmx), "path": os.path.abspath(args.product_tmx)})
    return lst

def render(rows, title, meta=None):
    seg_json = json.dumps(rows, ensure_ascii=False)
    out = re.sub(r"const SEG = \[[\s\S]*?\n\];", lambda m: "const SEG = " + seg_json + ";", tpl_src, count=1)
    out = out.replace("DomoStats Connector <span class=\"demoflag\">DEMO</span>", html.escape(title))
    if meta is not None:
        mj = json.dumps(meta, ensure_ascii=False)
        out = re.sub(r"const META = [\s\S]*?;\s*/\*__META__\*/",
                     lambda m: "const META = " + mj + ";  /*__META__*/", out, count=1)
    return out

def _sanitize_rel(rel):
    """Sanitize a manifest 'rel' into a safe relative path (keeps '/' as sub-folders)."""
    rel = (rel or "").replace("\\", "/")
    parts = []
    for seg in rel.split("/"):
        if seg in ("", ".", ".."):
            continue
        parts.append(re.sub(r'[:*?"<>|]+', "_", seg).strip() or "_")
    return "/".join(parts) or "article"

def out_path_for(src_path, title):
    if args.out and not batch:
        return args.out
    if args.source_manifest:
        rel = rel_of.get(os.path.abspath(src_path)) or (title or os.path.splitext(os.path.basename(src_path))[0])
        p = os.path.join(args.out_dir, _sanitize_rel(rel) + ".html")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        return p
    stem = title or os.path.splitext(os.path.basename(src_path))[0]
    safe = re.sub(r'[\\/:*?"<>|]+', "_", stem).strip() or "article"
    return os.path.join(args.out_dir, "TM-Match-Explorer-%s.html" % safe)

# ---- run over all sources ----
combined = []          # merged mt-todo with global ids
articles = []          # manifest of processed articles
gi = 0
for si, sp in enumerate(srcs):
    print("\n[%d/%d] %s" % (si+1, len(srcs), os.path.basename(sp)), flush=True)
    uids = None
    if os.path.splitext(sp)[1].lower() == ".json":
        if json_io is None:
            print("  ERROR: json_io 未読込のため .json を処理できません", flush=True); sys.exit(1)
        units = json_io.extract(sp)
        src = [u["text"] for u in units]
        uids = [u["uid"] for u in units]
        try:
            ftitle = (json.load(open(sp, encoding="utf-8-sig")).get("app_name", "")
                      or os.path.splitext(os.path.basename(sp))[0])
        except Exception:
            ftitle = os.path.splitext(os.path.basename(sp))[0]
    else:
        src, ftitle = read_segments(sp)
    title = (args.title if (not batch and args.title) else "") or ftitle or os.path.splitext(os.path.basename(sp))[0]
    print("  source segs:", len(src), flush=True)
    rows, mt_todo = analyze(src)
    if uids is not None:   # .json: 各 SEG 行に保護タグ（{n}→元タグ）を添付（編集画面のチップ用）
        for i, u in enumerate(units):
            if i < len(rows):
                rows[i]["tags"] = u.get("tags", {})
    bc = Counter(r["b"] for r in rows)
    print("  bands:", dict(bc), "| MT(<=74%):", len(mt_todo), flush=True)

    outp = out_path_for(sp, title)
    meta = {
        "source": {"name": os.path.basename(sp), "path": os.path.abspath(sp)},
        "output": {"name": os.path.basename(outp), "path": os.path.abspath(outp)},
        "tms": tm_list(),
        "project": {"name": (args.project_name or title or ""), "detail": args.project_detail or ""},
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "runMT": str(args.run_mt).strip() not in ("0", "false", "False", ""),
        "useNotapproved": _USE_UNAPP,
    }
    open(outp, "w", encoding="utf-8", newline="\n").write(render(rows, title, meta))
    print("  saved:", outp, flush=True)

    # .json ソースは uid マップ（SEG index -> JSON内 uid）を出力 → 後で TEP 確定訳を JSON へ復元
    if uids is not None:
        json.dump({"json": os.path.abspath(sp), "uids": uids},
                  open(outp + ".uidmap.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("  uidmap:", outp + ".uidmap.json", flush=True)

    # Unique key per article: relative path under --out-dir (so same-named files in
    # different sub-folders don't collide); falls back to the bare stem otherwise.
    if args.out_dir:
        rel_art = os.path.relpath(outp, args.out_dir)
        art_key = os.path.splitext(rel_art)[0].replace("\\", "/").replace("/", "__")
    else:
        art_key = os.path.splitext(os.path.basename(outp))[0]
    # per-article mt-todo (beta1-compatible)
    todo_path = outp + ".mt-todo.json"
    json.dump({"source": sp, "title": title, "count": len(mt_todo), "segments": mt_todo},
              open(todo_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("  mt-todo:", todo_path, flush=True)

    articles.append({"art": art_key, "html": outp, "title": title, "source": sp,
                     "segs": len(src), "mt": len(mt_todo)})
    for e in mt_todo:
        combined.append({"gi": gi, "art": art_key, "i": e["i"], "en": e["en"],
                         "pct": e["pct"], "glossary": e["glossary"],
                         "tm_candidates": e.get("tm_candidates", [])})
        gi += 1

# ---- combined MT to-do (feature 3) ----
if args.combined_todo:
    payload = {"count": len(combined), "articles": articles, "segments": combined}
    json.dump(payload, open(args.combined_todo, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("\ncombined mt-todo:", args.combined_todo, "| total MT segs:", len(combined), flush=True)

print("\nDONE. articles: %d | total MT to translate: %d" % (len(articles), len(combined)), flush=True)
