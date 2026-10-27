# -*- coding: utf-8 -*-
"""Kotonoha beta6.00 — スタンドアロンの TMX 入出力（argparse 非依存）。
ダッシュボードの「TM」タブ（TMエントリの一覧/検索/編集/削除）から使う。
蓄積型（同一原文の複数版）を保持する点は tm_writeback.load_tmx/write_tmx と同じ。
編集対象は書込可能TM（小さめ・XTM 読み取り専用は対象外）を想定。書込前に日付きバックアップ。"""
import os, time, html
import xml.etree.ElementTree as ET

VERSION = "beta6.00"


def _strip(tag):
    return tag.split("}")[-1]


def _text_of(el):
    return "".join(el.itertext())


def load_tmx(path, src_lang="en", tgt_lang="ja"):
    """src -> [ {tgt,prev,next,creationdate,changedate}, ... ]（挿入順を保持）。"""
    od = {}
    if not path or not os.path.exists(path):
        return od
    root = ET.parse(path).getroot()
    sp = src_lang[:2].lower(); tp = tgt_lang[:2].lower()
    for tu in root.iter():
        if _strip(tu.tag) != "tu":
            continue
        en = ja = None; prev = nxt = ""
        cdate = tu.attrib.get("creationdate", ""); chdate = tu.attrib.get("changedate", "")
        for ch in tu:
            ct = _strip(ch.tag)
            if ct == "prop":
                pt = ch.attrib.get("type", "")
                if pt == "x-previous-source-text":
                    prev = _text_of(ch)
                elif pt == "x-next-source-text":
                    nxt = _text_of(ch)
            elif ct == "tuv":
                lang = (ch.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
                        or ch.attrib.get("lang") or "")
                seg = "".join(_text_of(s) for s in ch if _strip(s.tag) == "seg")
                if lang.lower().startswith(sp):
                    en = seg
                elif lang.lower().startswith(tp):
                    ja = seg
        if en is not None and ja is not None:
            lst = od.setdefault(en.strip(), [])
            found = None
            for v in lst:
                if v["tgt"] == ja:
                    found = v; break
            if found is None:
                lst.append({"tgt": ja, "prev": prev, "next": nxt,
                            "creationdate": cdate, "changedate": chdate})
            else:
                if chdate > found.get("changedate", ""):
                    found["changedate"] = chdate
    return od


def _xesc(s):
    return html.escape(s or "", quote=False)


def write_tmx(path, od, src_lang="en-US", tgt_lang="ja-JP"):
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tmx version="1.4">',
             '  <header creationtool="Kotonoha" creationtoolversion="%s" segtype="sentence" '
             'o-tmf="Kotonoha" adminlang="en-US" srclang="%s" datatype="plaintext"/>' % (VERSION, src_lang),
             '  <body>']
    for src, versions in od.items():
        for v in sorted(versions, key=lambda x: (x.get("changedate") or x.get("creationdate") or "")):
            chdate = v.get("changedate") or now
            cdate = v.get("creationdate") or chdate
            lines.append('    <tu creationdate="%s" changedate="%s" creationid="Kotonoha-TEP">' % (cdate, chdate))
            if v.get("prev"):
                lines.append('      <prop type="x-previous-source-text">%s</prop>' % _xesc(v["prev"]))
            if v.get("next"):
                lines.append('      <prop type="x-next-source-text">%s</prop>' % _xesc(v["next"]))
            lines.append('      <tuv xml:lang="%s"><seg>%s</seg></tuv>' % (src_lang, _xesc(src)))
            lines.append('      <tuv xml:lang="%s"><seg>%s</seg></tuv>' % (tgt_lang, _xesc(v["tgt"])))
            lines.append('    </tu>')
    lines += ['  </body>', '</tmx>', '']
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))


def backup(path):
    """書込前に日付きバックアップを作成（存在時のみ）。"""
    if path and os.path.exists(path):
        bak = "%s.bak_%s.tmx" % (os.path.splitext(path)[0], time.strftime("%Y%m%d-%H%M%S"))
        try:
            import shutil
            shutil.copy2(path, bak)
            return bak
        except Exception:
            return ""
    return ""


def count(path):
    try:
        od = load_tmx(path)
        return sum(len(v) for v in od.values())
    except Exception:
        return None


def search(path, q="", limit=500):
    """q（EN/JA部分一致・大小無視）に合う版を返す。q 空なら先頭から limit 件。"""
    od = load_tmx(path)
    ql = (q or "").strip().lower()
    out = []
    for src, versions in od.items():
        for v in versions:
            if ql and (ql not in src.lower()) and (ql not in (v.get("tgt") or "").lower()):
                continue
            out.append({"src": src, "tgt": v.get("tgt", ""),
                        "changedate": v.get("changedate", ""), "creationdate": v.get("creationdate", "")})
            if len(out) >= limit:
                return out
    return out


def add(path, src, tgt):
    src = (src or "").strip()
    if not src or not (tgt or "").strip():
        return {"ok": False, "error": "src/tgt が空です"}
    od = load_tmx(path)
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    lst = od.setdefault(src, [])
    for v in lst:
        if v["tgt"] == tgt:
            return {"ok": True, "unchanged": True}
    lst.append({"tgt": tgt, "prev": "", "next": "", "creationdate": now, "changedate": now})
    backup(path)
    write_tmx(path, od)
    return {"ok": True, "added": True}


def update(path, old_src, old_tgt, new_src, new_tgt):
    """(old_src, old_tgt) の版を (new_src, new_tgt) に変更。old_src 空なら新規追加。"""
    old_src = (old_src or "").strip(); new_src = (new_src or "").strip()
    if not old_src:
        return add(path, new_src, new_tgt)
    if not new_src or not (new_tgt or "").strip():
        return {"ok": False, "error": "src/tgt が空です"}
    od = load_tmx(path)
    lst = od.get(old_src)
    if not lst:
        return {"ok": False, "error": "原文が見つかりません"}
    ver = None
    for v in lst:
        if v["tgt"] == old_tgt:
            ver = v; break
    if ver is None:
        return {"ok": False, "error": "対象の訳が見つかりません"}
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    if new_src == old_src:
        ver["tgt"] = new_tgt; ver["changedate"] = now
    else:
        lst.remove(ver)
        if not lst:
            od.pop(old_src, None)
        ver["tgt"] = new_tgt; ver["changedate"] = now
        od.setdefault(new_src, []).append(ver)
    backup(path)
    write_tmx(path, od)
    return {"ok": True, "updated": True}


def delete(path, src, tgt):
    src = (src or "").strip()
    od = load_tmx(path)
    lst = od.get(src)
    if not lst:
        return {"ok": False, "error": "原文が見つかりません"}
    before = len(lst)
    lst[:] = [v for v in lst if v["tgt"] != tgt]
    if len(lst) == before:
        return {"ok": False, "error": "対象の訳が見つかりません"}
    if not lst:
        od.pop(src, None)
    backup(path)
    write_tmx(path, od)
    return {"ok": True, "deleted": before - len(lst)}
