# -*- coding: utf-8 -*-
"""Produce a translated copy of each source file IN ITS ORIGINAL FORMAT by applying
the TM(s) sentence-by-sentence (exact / 100% matches).

This is the round-trip OUTPUT stage. Run it AFTER pre-translation + MT + TEP writeback,
so the TM already holds the confirmed translations for the content; any sentence not in
the TM is left as source text (or wrapped with 〔未訳〕 when --mark-missing). Formats are
handled by doc_io (Phase 1: .txt). Reuses tm_index (norm / exact_target) so lookups match
exactly how the analysis engine keys the TM.

Usage:
  python doc_export.py --source a.txt [b.txt ...] --tmx main.tmx [--sub-tmx s.tmx ...] \
                       --out-dir OUT [--cache-dir DIR] [--mark-missing]
  python doc_export.py --source-manifest m.json --tmx main.tmx --out-dir OUT
Outputs to  OUT/translated/<rel or basename>  keeping the original extension.
"""
import argparse, os, sys, io, json, re

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import tm_index
from tm_index import norm
import doc_io

HERE = os.path.dirname(os.path.abspath(__file__))

# Same sentence split as the analysis engine's read_segments, so keys line up.
_SENT = re.compile(r"(?<=[.!?。！？])\s+")


def split_sentences(text):
    out = []
    for s in _SENT.split(text):
        s = re.sub(r"\s+", " ", s).strip()
        if s:
            out.append(s)
    return out or ([text.strip()] if text.strip() else [])


ap = argparse.ArgumentParser()
ap.add_argument("--source", nargs="*", default=[], help="one or more source files")
ap.add_argument("--source-manifest", dest="source_manifest", default="",
                help='JSON {"sources":[{"src":<abs>,"rel":<output stem>}]} (keeps hierarchy)')
ap.add_argument("--tmx", required=True, help="primary / main TM")
ap.add_argument("--sub-tmx", dest="sub_tmx", nargs="*", default=[], help="extra match TM(s)")
ap.add_argument("--cache-dir", dest="cache_dir", default="", help="index cache folder")
ap.add_argument("--out-dir", dest="out_dir", required=True, help="output root (writes OUT/translated/...)")
ap.add_argument("--mark-missing", dest="mark_missing", action="store_true",
                help="wrap untranslated sentences with 〔未訳〕 instead of leaving source as-is")
a = ap.parse_args()

# ---- collect sources (+ rel for hierarchy, like the engine's manifest) ----
rel_of = {}
sources = []
if a.source_manifest:
    man = json.load(open(a.source_manifest, encoding="utf-8-sig"))
    entries = man.get("sources", man) if isinstance(man, dict) else man
    for e in entries:
        sp = e["src"] if isinstance(e, dict) else e
        sources.append(sp)
        if isinstance(e, dict) and e.get("rel"):
            rel_of[os.path.abspath(sp)] = e["rel"]
sources += list(a.source)
srcs = [p for p in sources if os.path.isfile(p)]
if not srcs:
    print("ERROR: no source files (use --source ... or --source-manifest ...)", flush=True)
    sys.exit(1)

# ---- build / load the index (match sources only; product TM not needed for output) ----
specs = [(a.tmx, False)] + [(s, False) for s in (a.sub_tmx or []) if s]
idx = tm_index.load_or_build(specs, a.cache_dir, log=lambda *x: print(*x, flush=True))
exact = idx.exact_target

MARK = "〔未訳〕"  # 〔未訳〕


def translate_unit(text):
    """Return (translated_text, hits, n_sentences). Exact TM matches only."""
    sents = split_sentences(text)
    out = []
    hit = 0
    for s in sents:
        t = exact.get(norm(s))
        if t:
            out.append(t); hit += 1
        else:
            out.append((MARK + s) if a.mark_missing else s)
    return " ".join(out), hit, len(sents)


total_s = total_hit = nfiles = skipped = 0
for sp in srcs:
    ext = os.path.splitext(sp)[1].lower()
    if not doc_io.supported(ext):
        print("SKIP (未対応形式 %s): %s" % (ext or "?", os.path.basename(sp)), flush=True)
        skipped += 1
        continue
    units = doc_io.extract(sp)
    trans = {}
    fhit = fseg = 0
    for u in units:
        tr, hit, nseg = translate_unit(u["text"])
        trans[u["uid"]] = tr
        fhit += hit; fseg += nseg
    rel = (rel_of.get(os.path.abspath(sp)) or os.path.basename(sp)).replace("\\", "/")
    if not os.path.splitext(rel)[1]:
        rel += ext                     # manifest rel is extension-less; keep original ext
    out_path = os.path.join(a.out_dir, "translated", rel)
    doc_io.apply(sp, out_path, trans)
    nfiles += 1; total_s += fseg; total_hit += fhit
    print("  %s -> %s  (文 %d/%d 訳出)" % (os.path.basename(sp), out_path, fhit, fseg), flush=True)

pct = (100.0 * total_hit / total_s) if total_s else 0.0
print("DONE. %d ファイル出力 / 文 %d 中 %d 訳出 (%.0f%%)%s"
      % (nfiles, total_s, total_hit, pct,
         ("  未対応 %d 件スキップ" % skipped) if skipped else ""), flush=True)
