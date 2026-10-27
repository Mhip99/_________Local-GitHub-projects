# -*- coding: utf-8 -*-
"""Format-aware extract / apply for ROUND-TRIP translation output.

The analysis engine (tm_match_analysis.py) throws away document structure when it
segments text for TM matching, so it cannot rebuild a translated file. This module is
the position-preserving layer used by doc_export.py to emit a translated copy *in the
original format*:

  extract(path) -> [ {"uid": <stable anchor>, "text": <translatable text>} , ... ]
  apply(path, out_path, trans)  -> writes a translated copy; for every unit whose uid
                                   is in `trans`, that unit's text is replaced by the
                                   translation, and everything else is preserved.

Phase 1 implements plain text (.txt). docx / xlsx / pptx / etc. register into REGISTRY
later (each needs python-docx / openpyxl / python-pptx; PDF and legacy binaries are
deferred). Keep each extractor's uid scheme stable so apply() can re-locate the unit.
"""
import os


# ---------- plain text (.txt) ----------
# A unit is one non-blank line (uid = "l<lineindex>"). apply() re-reads the original,
# preserves blank lines / indentation / newline style, and swaps in each translation.
def _txt_newline(raw):
    return "\r\n" if "\r\n" in raw else "\n"


def _txt_extract(path):
    raw = open(path, encoding="utf-8-sig").read()
    nl = _txt_newline(raw)
    units = []
    for i, ln in enumerate(raw.split(nl)):
        if ln.strip():
            units.append({"uid": "l%d" % i, "text": ln.strip()})
    return units


def _txt_apply(path, out_path, trans):
    raw = open(path, encoding="utf-8-sig").read()
    nl = _txt_newline(raw)
    lines = raw.split(nl)
    for i, ln in enumerate(lines):
        uid = "l%d" % i
        if uid in trans and ln.strip():
            lead = ln[:len(ln) - len(ln.lstrip())]   # keep the line's indentation
            lines[i] = lead + trans[uid]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    # newline="" so we control the line separator exactly (no CRLF doubling)
    open(out_path, "w", encoding="utf-8", newline="").write(nl.join(lines))


# ---------- Domo アプリ コンテンツ (.json)  [json_io に委譲] ----------
def _json_extract(path):
    import json_io
    return json_io.extract(path)

def _json_apply(path, out_path, trans):
    import json_io
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    return json_io.apply(path, out_path, trans)


# ---------- Word (.docx)  [python-docx] ----------
def _docx_iter(doc):
    """(uid, paragraph) を安定順に列挙（本文→表セル）。extract/apply で同一順＝uid 一致。"""
    for i, p in enumerate(doc.paragraphs):
        yield ("p%d" % i, p)
    for ti, tbl in enumerate(doc.tables):
        for ri, row in enumerate(tbl.rows):
            for ci, cell in enumerate(row.cells):
                for pi, p in enumerate(cell.paragraphs):
                    yield ("t%d_%d_%d_%d" % (ti, ri, ci, pi), p)

def _docx_set(p, text):
    if p.runs:
        p.runs[0].text = text
        for r in p.runs[1:]:
            r.text = ""
    else:
        p.text = text

def _docx_extract(path):
    import docx
    doc = docx.Document(path)
    out = []
    for uid, p in _docx_iter(doc):
        t = (p.text or "").strip()
        if t:
            out.append({"uid": uid, "text": t})
    return out

def _docx_apply(path, out_path, trans):
    import docx
    doc = docx.Document(path)
    for uid, p in _docx_iter(doc):
        if uid in trans and (p.text or "").strip():
            _docx_set(p, trans[uid])
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.save(out_path)


# ---------- Excel (.xlsx)  [openpyxl] ----------
def _xlsx_extract(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=False)
    out = []
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                if isinstance(v, str) and v.strip() and not v.lstrip().startswith("="):
                    out.append({"uid": "%s!%s" % (ws.title, cell.coordinate), "text": v.strip()})
    return out

def _xlsx_apply(path, out_path, trans):
    import openpyxl
    wb = openpyxl.load_workbook(path, data_only=False)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for cell in row:
                v = cell.value
                uid = "%s!%s" % (ws.title, cell.coordinate)
                if uid in trans and isinstance(v, str) and v.strip() and not v.lstrip().startswith("="):
                    cell.value = trans[uid]
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    wb.save(out_path)


# ---------- registry ----------
REGISTRY = {
    ".txt":  {"extract": _txt_extract,  "apply": _txt_apply,  "label": "text"},
    ".json": {"extract": _json_extract, "apply": _json_apply, "label": "Domo app JSON"},
    ".docx": {"extract": _docx_extract, "apply": _docx_apply, "label": "Word"},
    ".xlsx": {"extract": _xlsx_extract, "apply": _xlsx_apply, "label": "Excel"},
}


def supported(ext):
    return (ext or "").lower() in REGISTRY


def supported_exts():
    return sorted(REGISTRY.keys())


def extract(path):
    return REGISTRY[os.path.splitext(path)[1].lower()]["extract"](path)


def apply(path, out_path, trans):
    return REGISTRY[os.path.splitext(path)[1].lower()]["apply"](path, out_path, trans)
