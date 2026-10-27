# -*- coding: utf-8 -*-
"""TMX index builder with on-disk cache (Kotonoha beta2, feature (1)).

Builds the same index the beta1 engine built inline (exact_target / ice_ctx /
inv / keys / product_terms) but stores it to a pickle keyed by a fingerprint of
the input TMX files (abs path + size + mtime). If the TMX set is unchanged the
index is loaded from disk in seconds instead of re-parsing ~600 MB of XML.

The produced index is byte-for-byte equivalent to what beta1 built, so analysis
output is unchanged -- this is a pure speed-up.
"""
import os, re, io, sys, json, time, pickle, hashlib
import xml.etree.ElementTree as ET

# Bump when the index schema or normalization below changes, to auto-invalidate
# any cache written by an older build.
FORMAT_VERSION = "kotonoha-idx-3"

TOKCAP = 4000
TERM_MAXTOK = 4            # Product entries with <= this many tokens are UI terms

XTAG = re.compile(r"<[^>]+>")

def norm(s):
    s = XTAG.sub(" ", s or "")
    s = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_`#>|~]", " ", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s

def h(s):
    return hashlib.md5(s.encode("utf-8")).hexdigest()[:12]

# stopwords / function words: too noisy to be useful glossary hints as single tokens
STOP = frozenset("""a an the this that these those and or but of to in on at by for with from as is
are was were be been being it you your we our they their he she his her him them i me my
do does did done has have had having will would can could should may might must not no yes if then
than so such about into over under out up down off here there when where which who whom whose
what how why all any each every some more most other per via etc""".split())

def term_ok(k, ja):
    """Accept a Product entry as a glossary term only if it is genuinely term-like."""
    if not ja or len(ja) > 24:
        return False
    toks = k.split()
    if not (1 <= len(toks) <= TERM_MAXTOK):
        return False
    if len(toks) == 1:
        if toks[0] in STOP or len(toks[0]) < 3:
            return False
    return True


class Index:
    """Container for the matching index. Picklable."""
    __slots__ = ("exact_target", "exact_hist", "ice_ctx", "inv", "keys", "product_terms", "meta")
    def __init__(self):
        self.exact_target = {}   # norm_src -> target text (newest when multiple versions)
        self.exact_hist = {}     # norm_src -> [{"ja": target, "date": changedate}, ...] 版履歴
        self.ice_ctx = {}        # norm_src -> set of (prev_hash, next_hash)
        self.inv = {}            # token -> list of key ids (capped)
        self.keys = []           # id -> norm_src
        self.product_terms = {}  # norm_en (<=4 tok) -> {"en": surface, "ja": target}
        self.meta = {}           # build info (version, tmx list, timing)

# Pin the pickled class to module "tm_index" even when this file is run as a
# script (__main__), so a cache written by `python tm_index.py` unpickles fine
# from `import tm_index` in tm_match_analysis.py / inject_mt.py.
Index.__module__ = "tm_index"


def _index_tmx(idx, path, is_product, log=print):
    exact_target = idx.exact_target; ice_ctx = idx.ice_ctx
    inv = idx.inv; keys = idx.keys; product_terms = idx.product_terms
    exact_hist = idx.exact_hist
    strip = lambda t: t.split("}")[-1]
    n_tu = 0
    context = ET.iterparse(path, events=("end",))
    for ev, el in context:
        tag = strip(el.tag)
        if tag != "tu":
            continue
        n_tu += 1
        en = ja = None; prev = nxt = ""
        date = el.attrib.get("changedate") or el.attrib.get("creationdate") or ""
        for ch in el:
            ct = strip(ch.tag)
            if ct == "prop":
                pt = ch.attrib.get("type", "")
                if pt == "x-previous-source-text": prev = ch.text or ""
                elif pt == "x-next-source-text": nxt = ch.text or ""
            elif ct == "tuv":
                lang = ch.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or ch.attrib.get("lang") or ""
                seg = "".join("".join(s.itertext()) for s in ch if strip(s.tag) == "seg")
                if lang.lower().startswith("en"): en = seg
                elif lang.lower().startswith("ja"): ja = seg
        if en is not None and ja is not None:
            k = norm(en)
            if k:
                # 版履歴を蓄積（同一 ja は重複排除し最新 date を保持）。build_index 後段で
                # 複数版キーの exact_target を最新 date に差し替える（newest-wins）。
                hist = exact_hist.setdefault(k, [])
                rec = None
                for r in hist:
                    if r["ja"] == ja:
                        rec = r; break
                if rec is None:
                    hist.append({"ja": ja, "date": date})
                elif date > rec["date"]:
                    rec["date"] = date
                if k not in exact_target:
                    exact_target[k] = ja
                    kid = len(keys); keys.append(k)
                    for tok in set(k.split()):
                        lst = inv.setdefault(tok, [])
                        if len(lst) < TOKCAP: lst.append(kid)
                elif is_product and len(k.split()) <= TERM_MAXTOK:
                    exact_target[k] = ja
                if prev or nxt:
                    ice_ctx.setdefault(k, set()).add((h(norm(prev)), h(norm(nxt))))
                if is_product:
                    toks = k.split()
                    if 1 <= len(toks) <= TERM_MAXTOK and k not in product_terms and term_ok(k, ja):
                        product_terms[k] = {"en": XTAG.sub(" ", en).strip(), "ja": ja}
        el.clear()
        if n_tu % 100000 == 0:
            log("  ", os.path.basename(path), "TU", n_tu, "keys", len(keys))
    log("  done", os.path.basename(path), "TU", n_tu, "keys", len(keys))
    return n_tu


def _spec_fingerprint(specs):
    """specs = list of (path, is_product). Fingerprint = version + each file's
    abspath + size + mtime_ns + role. Any TMX change -> different fingerprint."""
    parts = [FORMAT_VERSION]
    for path, is_product in specs:
        st = os.stat(path)
        parts.append("%s|%d|%d|%d" % (os.path.abspath(path).lower(),
                                      st.st_size, st.st_mtime_ns, int(is_product)))
    blob = "\n".join(parts)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()[:16]


def build_index(specs, log=print):
    """Build a fresh Index from specs = list of (path, is_product)."""
    idx = Index()
    t0 = time.time()
    for path, is_product in specs:
        role = "Product" if is_product else "primary"
        log("indexing %s TMX (streaming): %s" % (role, os.path.basename(path)))
        _index_tmx(idx, path, is_product, log=log)
    # 複数版が蓄積した原文は、最新 date の訳を exact_target に採用（newest-wins）。
    # 単一版キー（大多数）は従来どおり（先勝ち/Product上書き）で無改修。
    multi = 0
    for k, hist in idx.exact_hist.items():
        if len(hist) > 1:
            best = max(hist, key=lambda r: (r.get("date") or ""))
            if best.get("date") and idx.exact_target.get(k) != best["ja"]:
                idx.exact_target[k] = best["ja"]; multi += 1
    idx.meta = {
        "version": FORMAT_VERSION,
        "built": time.strftime("%Y-%m-%d %H:%M:%S"),
        "build_seconds": round(time.time() - t0, 1),
        "tmx": [{"path": p, "is_product": ip, "size": os.path.getsize(p)} for p, ip in specs],
        "unique_keys": len(idx.keys),
        "product_terms": len(idx.product_terms),
    }
    log("TMX done. unique keys: %d | product terms: %d | %.1fs"
        % (len(idx.keys), len(idx.product_terms), idx.meta["build_seconds"]))
    return idx


def load_or_build(specs, cache_dir, no_cache=False, rebuild=False, log=print):
    """Return an Index for specs, using the on-disk cache when possible.

    specs      : list of (path, is_product)
    cache_dir  : folder holding idx_<fp>.pkl (+ .json sidecar)
    no_cache   : build in memory, do not read or write the cache
    rebuild    : ignore any existing cache entry and rebuild (then save)
    """
    fp = _spec_fingerprint(specs)
    if no_cache:
        log("cache: disabled (--no-cache); building in memory")
        return build_index(specs, log=log)

    os.makedirs(cache_dir, exist_ok=True)
    pkl = os.path.join(cache_dir, "idx_%s.pkl" % fp)
    side = os.path.join(cache_dir, "idx_%s.json" % fp)

    if os.path.exists(pkl) and not rebuild:
        t0 = time.time()
        try:
            with open(pkl, "rb") as f:
                idx = pickle.load(f)
            if getattr(idx, "meta", {}).get("version") == FORMAT_VERSION:
                log("cache HIT: %s (%.1f MB) loaded in %.1fs | keys %d"
                    % (os.path.basename(pkl), os.path.getsize(pkl) / 1e6,
                       time.time() - t0, len(idx.keys)))
                return idx
            log("cache STALE (version mismatch); rebuilding")
        except Exception as e:
            log("cache unreadable (%s); rebuilding" % e)

    log("cache MISS: building index for fingerprint %s" % fp)
    idx = build_index(specs, log=log)
    try:
        t0 = time.time()
        with open(pkl, "wb") as f:
            pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(side, "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fp, **idx.meta}, f, ensure_ascii=False, indent=1)
        log("cache SAVED: %s (%.1f MB) in %.1fs"
            % (os.path.basename(pkl), os.path.getsize(pkl) / 1e6, time.time() - t0))
    except Exception as e:
        log("WARNING: could not write cache (%s); continuing without saving" % e)
    return idx


if __name__ == "__main__":
    # CLI to pre-build / inspect the cache without running an analysis.
    import argparse
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser(description="Build or inspect the Kotonoha TMX index cache.")
    ap.add_argument("--tmx", required=True, help="primary TM (University)")
    ap.add_argument("--product-tmx", dest="product_tmx", default="")
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--rebuild", action="store_true", help="force rebuild even if cached")
    a = ap.parse_args()
    specs = [(a.tmx, False)]
    if a.product_tmx:
        specs.append((a.product_tmx, True))
    idx = load_or_build(specs, a.cache_dir, rebuild=a.rebuild)
    print("ready. keys:", len(idx.keys), "product terms:", len(idx.product_terms))
