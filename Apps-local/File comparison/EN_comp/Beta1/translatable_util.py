# -*- coding: utf-8 -*-
"""Translatable-text helpers for file comparison (--translatable-only mode).

Extracts the natural-language strings a translator actually works on (frontmatter
title + body prose), stripping MDX/Markdown markup so that changes to non-
translatable elements (imports, tags, list markers, indentation, code, URLs,
excerpt / other frontmatter) do NOT count as changes. Those ignored change
types are summarised for the Note column.
"""
import re

_FM = r'(?s)^\ufeff?\s*---\s*\n(.*?)\n---\s*\n?'

def _split_frontmatter(text):
    m = re.search(_FM, text)
    if m:
        return m.group(1), text[m.end():]
    return "", text

def _fm_field(fm, key):
    mm = re.search(r'(?mi)^\s*' + re.escape(key) + r'\s*:\s*(.+?)\s*$', fm)
    return mm.group(1).strip().strip('"\'') if mm else None

def _project_line(s):
    """Reduce one body line to its translatable text (markup removed)."""
    s = re.sub(r'`[^`]*`', ' ', s)                       # inline code
    s = re.sub(r'!\[([^\]]*)\]\([^)]*\)', r' \1 ', s)      # image -> alt text
    s = re.sub(r'\[([^\]]*)\]\([^)]*\)', r' \1 ', s)       # link  -> link text
    s = re.sub(r'\{[^}]*\}', ' ', s)                     # JSX expressions
    s = re.sub(r'</?[A-Za-z][^>]*>', ' ', s)             # HTML/MDX tags
    if re.match(r'^\s*:?-{3,}:?\s*$', s):                # hr / table separator
        return ''
    s = re.sub(r'^\s{0,3}#{1,6}\s*', ' ', s)             # heading markers
    s = re.sub(r'^\s*>+\s?', ' ', s)                     # blockquote
    s = re.sub(r'^\s*([-*+]|\d+\.)\s+', ' ', s)          # list markers
    s = s.replace('|', ' ')                              # table pipes
    s = re.sub(r'[*_~]', '', s)                          # emphasis chars
    return ' '.join(s.split())

def translatable(text):
    """Return (title, [translatable body lines])."""
    fm, body = _split_frontmatter(text)
    title = _fm_field(fm, 'title') or ""
    body = re.sub(r'(?s)```.*?```', ' ', body)           # fenced code
    body = re.sub(r'(?s)~~~.*?~~~', ' ', body)
    body = re.sub(r'(?m)^\s*(?:import|export)\s.*$', ' ', body)
    out = []
    for ln in body.split('\n'):
        p = _project_line(ln)
        if p:
            out.append(p)
    return title, out

def ignored_categories(old, new):
    """Labels for non-translatable differences between two raw file texts."""
    labels = []
    ofm, _ = _split_frontmatter(old)
    nfm, _ = _split_frontmatter(new)
    if _fm_field(ofm, 'excerpt') != _fm_field(nfm, 'excerpt'):
        labels.append('excerpt')
    def fm_other(fm):
        d = {}
        for mm in re.finditer(r'(?mi)^\s*([\w-]+)\s*:\s*(.*)$', fm):
            k = mm.group(1).lower()
            if k not in ('title', 'excerpt'):
                d[k] = mm.group(2).strip()
        return d
    if fm_other(ofm) != fm_other(nfm):
        labels.append('frontmatter')
    imp = lambda t: frozenset(re.findall(r'(?m)^\s*(?:import|export)\s.*$', t))
    if imp(old) != imp(new):
        labels.append('import')
    bullets = lambda t: (bool(re.search(r'(?m)^\s*\*\s+\S', t)),
                         bool(re.search(r'(?m)^\s*\+\s+\S', t)),
                         bool(re.search(r'(?m)^\s*-\s+\S', t)))
    if bullets(old) != bullets(new):
        labels.append('list marker')
    tags = lambda t: tuple(re.findall(r'</?[A-Za-z][^>]*>', t))
    if tags(old) != tags(new):
        labels.append('tag/markup')
    urls = lambda t: frozenset(re.findall(r'\]\(([^)]+)\)', t) +
                               re.findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', t))
    if urls(old) != urls(new):
        labels.append('link/image path')
    code = lambda t: tuple(re.findall(r'(?s)```.*?```', t) + re.findall(r'`[^`]+`', t))
    if code(old) != code(new):
        labels.append('code')
    def norm_ws(t):
        ls = [l.strip() for l in t.replace('\r\n', '\n').replace('\r', '\n').split('\n')]
        return '\n'.join([l for l in ls if l])
    if old != new and norm_ws(old) == norm_ws(new):
        labels.append('spacing/line break')
    seen = set(); out = []
    for l in labels:
        if l not in seen:
            out.append(l); seen.add(l)
    return out
