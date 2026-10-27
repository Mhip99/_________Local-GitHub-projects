# -*- coding: utf-8 -*-
"""Inject MT (AI) translations into TM-Match-Explorer HTML (Kotonoha beta2).

Two modes:

  SINGLE (beta1-compatible):
      python inject_mt.py --html OUT.html --mt OUT.html.mt-done.jsonl
    Fills each <=74% MT row from an mt-done file keyed by the per-article index `i`.

  BATCH (feature 3):
      python inject_mt.py --combined-todo combined.mt-todo.json --combined-mt combined.mt-done.jsonl
    One combined mt-done (lines keyed by global id `gi`) is fanned back into every
    article's HTML listed in the combined-todo manifest. No TMX needed -- fast.
"""
import argparse, re, sys, io, os, json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ap = argparse.ArgumentParser()
ap.add_argument("--html", default="", help="single mode: HTML from tm_match_analysis.py")
ap.add_argument("--mt", default="", help="single mode: mt-done keyed by per-article index i")
ap.add_argument("--out", default="", help="single mode: output (default: overwrite --html)")
ap.add_argument("--combined-todo", dest="combined_todo", default="",
                help="batch mode: combined.mt-todo.json written by tm_match_analysis.py")
ap.add_argument("--combined-mt", dest="combined_mt", default="",
                help="batch mode: combined mt-done keyed by global id gi")
args = ap.parse_args()

SEG_RE = r"const SEG = (\[[\s\S]*?\]);\s*\nconst (?:META|BANDS)"


def _load_records(path):
    """Yield dict records from JSONL, or JSON array, or JSON object."""
    txt = open(path, encoding="utf-8-sig").read().strip()
    if not txt:
        return
    try:
        obj = json.loads(txt)
        if isinstance(obj, dict):
            # a lone record {"i"/"gi":.., "ja":..} vs a mapping {index: ja}
            if "ja" in obj and ("i" in obj or "gi" in obj):
                yield obj
            else:
                for k, v in obj.items():
                    yield {"i": k, "ja": v if isinstance(v, str) else v.get("ja", "")}
            return
        if isinstance(obj, list):
            for e in obj:
                yield e
            return
    except (ValueError, KeyError, TypeError):
        pass
    for ln in txt.split("\n"):
        ln = ln.strip()
        if ln:
            yield json.loads(ln)


def _read_run_mt(html_txt):
    """作業ファイルの META.runMT を読む（既定 True）。False なら MT は翻訳欄ではなく履歴へ。"""
    m = re.search(r'"runMT"\s*:\s*(true|false)', html_txt)
    if m:
        return m.group(1) == "true"
    return True


def inject_into_html(html_path, index_to_ja, out_path=None):
    """index_to_ja: {int per-article index -> ja}. Returns (filled, out_of_range, still_empty).
    META.runMT が False のときは MT を翻訳欄(ja)ではなく履歴(hist)に「MT」項として入れる
    （翻訳欄は英語のまま＝未反映）。True のときは従来どおり ja に反映。"""
    html_txt = open(html_path, encoding="utf-8").read()
    run_mt = _read_run_mt(html_txt)
    m = re.search(SEG_RE, html_txt)
    if not m:
        raise RuntimeError("const SEG not found in %s" % html_path)
    seg = json.loads(m.group(1))
    filled = 0; missing = []
    for i, ja in index_to_ja.items():
        if 0 <= i < len(seg):
            if run_mt:
                seg[i]["ja"] = [["eq", ja]]; seg[i]["st"] = "mt"
            else:
                # 翻訳欄には入れず、履歴に「MT」項として先頭追加（重複は置換）
                seg[i]["st"] = "mt"
                hist = [h for h in (seg[i].get("hist") or []) if not h.get("mt")]
                hist.insert(0, {"ja": ja, "mt": True})
                seg[i]["hist"] = hist
            filled += 1
        else:
            missing.append(i)
    # 反映残り: runMT時は ja 空、非runMT時は MT履歴が無いもの
    if run_mt:
        still_empty = [idx for idx, s in enumerate(seg) if s.get("st") == "mt" and not s.get("ja")]
    else:
        still_empty = [idx for idx, s in enumerate(seg)
                       if s.get("st") == "mt" and not any(h.get("mt") for h in (s.get("hist") or []))]
    seg_json = json.dumps(seg, ensure_ascii=False)
    html_txt = html_txt[:m.start(1)] + seg_json + html_txt[m.end(1):]
    out = out_path or html_path
    open(out, "w", encoding="utf-8", newline="\n").write(html_txt)
    return filled, missing, still_empty, out, len(seg)


# ================= BATCH MODE =================
if args.combined_todo or args.combined_mt:
    if not (args.combined_todo and args.combined_mt):
        print("ERROR: batch mode needs BOTH --combined-todo and --combined-mt", flush=True); sys.exit(1)
    manifest = json.load(open(args.combined_todo, encoding="utf-8-sig"))
    # gi -> (art, i); art -> html path
    gi_map = {int(e["gi"]): (e["art"], int(e["i"])) for e in manifest["segments"]}
    art_html = {a["art"]: a["html"] for a in manifest["articles"]}

    ja_by_gi = {}
    for rec in _load_records(args.combined_mt):
        if "gi" in rec:
            ja_by_gi[int(rec["gi"])] = rec["ja"]
        elif "art" in rec and "i" in rec:
            # allow art+i keyed records too
            for g, (art, i) in gi_map.items():
                if art == rec["art"] and i == int(rec["i"]):
                    ja_by_gi[g] = rec["ja"]; break
    print("combined mt entries:", len(ja_by_gi), "| articles:", len(art_html), flush=True)

    # group by article
    per_art = {}
    unknown = 0
    for gi, ja in ja_by_gi.items():
        if gi in gi_map:
            art, i = gi_map[gi]
            per_art.setdefault(art, {})[i] = ja
        else:
            unknown += 1
    if unknown:
        print("  WARNING: %d mt records had unknown gi (skipped)" % unknown, flush=True)

    tot_filled = tot_empty = 0
    for art, html_path in art_html.items():
        idx_ja = per_art.get(art, {})
        if not os.path.exists(html_path):
            print("  MISSING HTML for %s: %s (skip)" % (art, html_path), flush=True); continue
        filled, missing, still_empty, out, nseg = inject_into_html(html_path, idx_ja)
        tot_filled += filled; tot_empty += len(still_empty)
        print("  %-40s filled %4d / rows %4d | still empty %d"
              % (art[:40], filled, nseg, len(still_empty)), flush=True)
    print("\nDONE. total filled: %d | total MT rows still empty: %d" % (tot_filled, tot_empty), flush=True)
    sys.exit(0)


# ================= SINGLE MODE =================
if not (args.html and args.mt):
    print("ERROR: single mode needs --html and --mt (or use --combined-todo/--combined-mt)", flush=True)
    sys.exit(1)

index_to_ja = {}
for rec in _load_records(args.mt):
    index_to_ja[int(rec["i"])] = rec["ja"]
print("mt entries:", len(index_to_ja), flush=True)

filled, missing, still_empty, out, nseg = inject_into_html(args.html, index_to_ja, args.out or None)
print("rows in HTML:", nseg, flush=True)
print("filled:", filled, "| out-of-range:", len(missing), "| MT rows still empty:", len(still_empty), flush=True)
if still_empty[:10]:
    print("  first empty MT indices:", still_empty[:10], flush=True)
print("saved:", out, flush=True)
