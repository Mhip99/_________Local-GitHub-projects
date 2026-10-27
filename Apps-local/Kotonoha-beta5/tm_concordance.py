# -*- coding: utf-8 -*-
"""Kotonoha beta5.01 — Concordance search（TMX横断検索）用の専用キャッシュ＆検索。
argparse 非依存。大きな TMX も ET.iterparse + el.clear() で省メモリ解析し、
原文EN・原文JA・更新日付の平坦リストを pickle キャッシュ（指紋=path+size+mtime）。
検索は EN/JA/両方・大小区別・複数キーワード AND/OR・正規表現に対応。"""
import os, re, time, pickle, hashlib
import xml.etree.ElementTree as ET

CONC_VERSION = "concv1"


def _strip(tag):
    return tag.split("}")[-1]


def fingerprint(path):
    st = os.stat(path)
    blob = "%s|%s|%d|%d" % (CONC_VERSION, os.path.abspath(path).lower(), st.st_size, st.st_mtime_ns)
    return hashlib.md5(blob.encode("utf-8")).hexdigest()[:16]


def cache_file(path, cache_dir):
    return os.path.join(cache_dir, "conc_%s.pkl" % fingerprint(path))


def is_built(path, cache_dir):
    try:
        return os.path.isfile(cache_file(path, cache_dir))
    except Exception:
        return False


def build(path, cache_dir, src_lang="en", tgt_lang="ja"):
    """TMX を走査して [{"en","ja","date"}] を作り pickle。戻り値=件数。"""
    if not (path and os.path.isfile(path)):
        return {"ok": False, "error": "TMが見つかりません: %s" % path, "count": 0}
    os.makedirs(cache_dir, exist_ok=True)
    sp = src_lang[:2].lower(); tp = tgt_lang[:2].lower()
    recs = []
    context = ET.iterparse(path, events=("end",))
    for ev, el in context:
        if _strip(el.tag) != "tu":
            continue
        en = ja = None
        cdate = el.attrib.get("changedate", "") or el.attrib.get("creationdate", "")
        for ch in el:
            if _strip(ch.tag) != "tuv":
                continue
            lang = (ch.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                    or ch.attrib.get("lang") or "")
            seg = "".join("".join(s.itertext()) for s in ch if _strip(s.tag) == "seg")
            ll = lang.lower()
            if ll.startswith(sp):
                en = seg
            elif ll.startswith(tp):
                ja = seg
        if en is not None and ja is not None:
            recs.append({"en": en, "ja": ja, "date": cdate})
        el.clear()
    out = cache_file(path, cache_dir)
    with open(out, "wb") as f:
        pickle.dump({"version": CONC_VERSION, "path": os.path.abspath(path), "recs": recs}, f,
                    protocol=pickle.HIGHEST_PROTOCOL)
    return {"ok": True, "count": len(recs), "cache": out}


def load(path, cache_dir):
    try:
        cf = cache_file(path, cache_dir)
        if not os.path.isfile(cf):
            return None
        with open(cf, "rb") as f:
            d = pickle.load(f)
        if d.get("version") != CONC_VERSION:
            return None
        return d.get("recs") or []
    except Exception:
        return None


def _make_matcher(q, field, case, regex, mode):
    """対象文字列を受け取り bool を返す関数を作る。失敗時 (None, error)。"""
    q = q or ""
    if regex:
        try:
            rx = re.compile(q, 0 if case else re.IGNORECASE)
        except re.error as e:
            return None, "正規表現エラー: %s" % e
        def m(text):
            return bool(rx.search(text or ""))
        return m, ""
    kws = [k for k in q.split() if k]
    if not kws:
        return (lambda text: False), ""
    if not case:
        kws = [k.lower() for k in kws]
    anymode = (mode == "or")
    def m(text):
        t = (text or "") if case else (text or "").lower()
        if anymode:
            return any(k in t for k in kws)
        return all(k in t for k in kws)
    return m, ""


def search(paths, q, field="both", case=False, regex=False, mode="and", limit=300, cache_dir=""):
    matcher, err = _make_matcher(q, field, case, regex, mode)
    if err:
        return {"ok": False, "error": err, "rows": [], "not_built": [], "truncated": False}
    rows = []; not_built = []; scanned = 0; truncated = False
    for p in paths:
        if not p:
            continue
        recs = load(p, cache_dir)
        if recs is None:
            not_built.append(os.path.basename(p)); continue
        name = os.path.basename(p)
        for r in recs:
            scanned += 1
            en = r.get("en", ""); ja = r.get("ja", "")
            if field == "en":
                hit = matcher(en)
            elif field == "ja":
                hit = matcher(ja)
            else:
                hit = matcher(en) or matcher(ja)
            if hit:
                rows.append({"en": en, "ja": ja, "tm": name, "date": r.get("date", "")})
                if len(rows) >= limit:
                    truncated = True
                    return {"ok": True, "rows": rows, "not_built": not_built,
                            "truncated": truncated, "scanned": scanned}
    return {"ok": True, "rows": rows, "not_built": not_built, "truncated": truncated, "scanned": scanned}
