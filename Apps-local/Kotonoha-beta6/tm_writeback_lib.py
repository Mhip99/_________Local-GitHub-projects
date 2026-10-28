# -*- coding: utf-8 -*-
"""TM 書き戻しの共通ロジック（副作用なし・argparse非依存）。

`tm_writeback.py`（CLI）と `projects.py` の TEP完了（/api/tep-complete）の両方から使う、
蓄積型 TMX マージの中核。インポートしても引数解析や stdout 差し替えなどの副作用は無い。

蓄積型: 同一原文の複数版（過去訳）を版リストとして保持し、新しい確定訳は
**既存を残したまま新しい <tu> として追記**する（上書きしない）。同一訳が既にあれば
changedate だけ更新する。TMX フォーマットは従来 `tm_writeback.py` と文字単位で同一。
"""
import os, html, time
import xml.etree.ElementTree as ET

_strip = lambda t: t.split("}")[-1]


def _text_of(el):
    return "".join(el.itertext()) if el is not None else ""


def xesc(s):
    return html.escape(s or "", quote=False)


def load_tmx(path, src_lang="en-US", tgt_lang="ja-JP"):
    """既存 TMX を src -> [ {tgt,prev,next,creationdate,changedate}, ... ] として読む。
    蓄積型: 同一原文の複数 <tu>（過去訳）をすべて版リストとして保持（同一 tgt は重複排除）。"""
    od = {}
    if not os.path.exists(path):
        return od
    try:
        root = ET.parse(path).getroot()
    except Exception:
        # 壊れた/読めない TMX は新規扱い（呼び出し側が書き直す）
        return od
    for tu in root.iter():
        if _strip(tu.tag) != "tu":
            continue
        en = ja = None; prev = nxt = ""
        cdate = tu.attrib.get("creationdate", ""); chdate = tu.attrib.get("changedate", "")
        for ch in tu:
            ct = _strip(ch.tag)
            if ct == "prop":
                pt = ch.attrib.get("type", "")
                if pt == "x-previous-source-text": prev = _text_of(ch)
                elif pt == "x-next-source-text": nxt = _text_of(ch)
            elif ct == "tuv":
                lang = ch.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or ch.attrib.get("lang") or ""
                seg = "".join(_text_of(s) for s in ch if _strip(s.tag) == "seg")
                if lang.lower().startswith(src_lang[:2]): en = seg
                elif lang.lower().startswith(tgt_lang[:2]): ja = seg
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
                if chdate > found.get("changedate", ""): found["changedate"] = chdate
                if prev and not found.get("prev"): found["prev"] = prev
                if nxt and not found.get("next"): found["next"] = nxt
    return od


def write_tmx(path, od, src_lang="en-US", tgt_lang="ja-JP"):
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<tmx version="1.4">',
             '  <header creationtool="Kotonoha" creationtoolversion="beta2" segtype="sentence" '
             'o-tmf="Kotonoha" adminlang="en-US" srclang="%s" datatype="plaintext"/>' % src_lang,
             '  <body>']
    for src, versions in od.items():
        # 原文ごとに版リストを古い順→新しい順で複数 <tu> として出力（各版が自分の日時を保持）
        for v in sorted(versions, key=lambda x: (x.get("changedate") or x.get("creationdate") or "")):
            chdate = v.get("changedate") or now
            cdate = v.get("creationdate") or chdate
            lines.append('    <tu creationdate="%s" changedate="%s" creationid="Kotonoha-TEP">' % (cdate, chdate))
            if v.get("prev"):
                lines.append('      <prop type="x-previous-source-text">%s</prop>' % xesc(v["prev"]))
            if v.get("next"):
                lines.append('      <prop type="x-next-source-text">%s</prop>' % xesc(v["next"]))
            lines.append('      <tuv xml:lang="%s"><seg>%s</seg></tuv>' % (src_lang, xesc(src)))
            lines.append('      <tuv xml:lang="%s"><seg>%s</seg></tuv>' % (tgt_lang, xesc(v["tgt"])))
            lines.append('    </tu>')
    lines += ['  </body>', '</tmx>', '']
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines))


def merge_entries(path, entries, src_lang="en-US", tgt_lang="ja-JP", dry_run=False):
    """entries = [{src,tgt,prev?,next?}, ...] を既存 TMX に蓄積マージして書き出す。
    既存訳は残したまま新しい確定訳を版として追記（上書きしない）。同一訳は changedate のみ更新。
    返り値: {existing, before, after, added, refreshed}。dry_run=True なら書き込まない。"""
    existing = os.path.exists(path)
    now = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    od = load_tmx(path, src_lang, tgt_lang)
    before = sum(len(v) for v in od.values()); added = refreshed = 0
    for e in entries:
        src = (e.get("src") or "").strip()
        tgt = (e.get("tgt") or "").strip()
        if not src or not tgt:
            continue
        lst = od.setdefault(src, [])
        ver = None
        for v in lst:
            if v["tgt"] == tgt:
                ver = v; break
        if ver is None:
            lst.append({"tgt": tgt, "prev": e.get("prev", ""), "next": e.get("next", ""),
                        "creationdate": now, "changedate": now})
            added += 1
        else:
            ver["changedate"] = now
            if e.get("prev") and not ver.get("prev"): ver["prev"] = e["prev"]
            if e.get("next") and not ver.get("next"): ver["next"] = e["next"]
            refreshed += 1
    after = sum(len(v) for v in od.values())
    if not dry_run and (added or refreshed):
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        write_tmx(path, od, src_lang, tgt_lang)
    return {"existing": existing, "before": before, "after": after,
            "added": added, "refreshed": refreshed}
