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


# ---------- registry ----------
REGISTRY = {
    ".txt": {"extract": _txt_extract, "apply": _txt_apply, "label": "text"},
}


def supported(ext):
    return (ext or "").lower() in REGISTRY


def supported_exts():
    return sorted(REGISTRY.keys())


def extract(path):
    return REGISTRY[os.path.splitext(path)[1].lower()]["extract"](path)


def apply(path, out_path, trans):
    return REGISTRY[os.path.splitext(path)[1].lower()]["apply"](path, out_path, trans)
