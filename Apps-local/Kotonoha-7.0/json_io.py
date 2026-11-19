# -*- coding: utf-8 -*-
"""Domo app-content JSON のための翻訳抽出 / 復元（Kotonoha 往復レイヤ）。

Domo の学習アプリ JSON（{"app_name", "pages":[{"name","displayName","fields":{...}}]}）の
**表示テキスト**（title/description/instructions/pinpoints/tasks/videos.subtext 等。pages[].name は内部キーで据置）
をブロック（<p>/<li>/<h*> 等）単位のセグメントに抽出し、翻訳後に元の構造・インラインタグを保ったまま
JSON へ戻す。インラインタグ（<strong>/<span>/<a>/<br> 等）は **番号プレースホルダ {1}{2}…** に退避し、
復元時にそのまま戻す（＝保護タグ。TEP 画面では編集不可・移動可のチップとして扱う）。

  extract(path) -> [ {"uid": <JSON内の安定位置#slot>, "text": <プレースホルダ入りテキスト>}, ... ]  （文書順）
  apply(path, out_path, trans)  -> uid→訳(プレースホルダ入り) を元 JSON に適用して翻訳済み JSON を書き出す

セグメント粒度は「1ブロック＝1セグメント」（文分割しない＝インラインタグをまたがない・往復 1:1）。
apply は元 JSON を再抽出して構造/タグを得るため、uid の対応さえ保てば順序ズレに強い。
"""
import json, re
from html.parser import HTMLParser

# 翻訳対象のフィールド（fields 配下）。pages[].name は内部キーのため対象外。
FIELD_KEYS = ("title", "description", "instructions")
LIST_FIELDS = {
    "pinpoints": ("header", "copy"),
    "tasks": ("label", "description", "copy"),
    "videos": ("subtext",),
    "modalVideos": ("title", "subtext", "caption"),
}

INLINE = {"strong", "b", "em", "i", "u", "span", "a", "code", "sub", "sup",
          "mark", "small", "br", "img", "wbr"}
BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
         "blockquote", "table", "thead", "tbody", "tr", "td", "th", "section", "header"}


class _Splitter(HTMLParser):
    """フィールドの HTML を「構造トークン」と「セグメントslot」に分解する。
    tokens: [('struct', raw_html), ('seg', {'text':.., 'tags':{n:tag}}), ...]
    インライン要素はセグメント内の {n} プレースホルダに退避（tags に元タグ文字列を保持）。"""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tokens = []
        self._cur = []      # 現在の inline run の断片（文字列 or ('ph', n)）
        self._tags = {}     # n -> 元タグ文字列
        self._n = 0

    def _flush(self):
        text = "".join(p if isinstance(p, str) else "{%d}" % p[1] for p in self._cur)
        if text.strip():
            self.tokens.append(("seg", {"text": re.sub(r"[ \t]+", " ", text).strip(),
                                        "tags": dict(self._tags)}))
        elif text:
            # 空白のみ → 構造として温存（レイアウト保持）
            self.tokens.append(("struct", text))
        self._cur = []
        self._tags = {}
        self._n = 0

    def handle_starttag(self, tag, attrs):
        if tag in INLINE:
            self._n += 1
            self._tags[self._n] = self.get_starttag_text()
            self._cur.append(("ph", self._n))
        else:
            self._flush()
            self.tokens.append(("struct", self.get_starttag_text()))

    def handle_startendtag(self, tag, attrs):   # <br/> 等
        if tag in INLINE:
            self._n += 1
            self._tags[self._n] = self.get_starttag_text()
            self._cur.append(("ph", self._n))
        else:
            self._flush()
            self.tokens.append(("struct", self.get_starttag_text()))

    def handle_endtag(self, tag):
        if tag in INLINE:
            if tag == "br":
                return
            self._n += 1
            self._tags[self._n] = "</%s>" % tag
            self._cur.append(("ph", self._n))
        else:
            self._flush()
            self.tokens.append(("struct", "</%s>" % tag))

    def handle_data(self, data):
        self._cur.append(data)

    def close(self):
        super().close()
        self._flush()


def split_field(html):
    """HTML文字列 -> tokens（上記）。純テキスト（タグ無し）は 1 seg になる。"""
    p = _Splitter()
    p.feed(html or "")
    p.close()
    return p.tokens


def _restore(text, tags):
    """訳テキスト中の {n} を元タグへ復元（翻訳者が順序を入れ替えていてもそのまま戻す）。"""
    def sub(m):
        return tags.get(int(m.group(1)), "")
    return re.sub(r"\{(\d+)\}", sub, text or "")


def rebuild_field(tokens, trans_for_field):
    """tokens を HTML に戻す。seg slot は trans_for_field[slotidx]（あれば訳、無ければ原文）。"""
    out = []
    slot = 0
    for kind, val in tokens:
        if kind == "struct":
            out.append(val)
        else:  # seg
            tr = trans_for_field.get(slot)
            src_text = val["text"]
            out.append(_restore(tr if tr is not None else src_text, val["tags"]))
            slot += 1
    return "".join(out)


def _field_refs(j):
    """翻訳対象フィールドを (fieldpath, container_dict, key) で列挙（文書順）。"""
    refs = []
    if isinstance(j.get("app_name"), str):
        refs.append(("app_name", j, "app_name"))
    for pi, pg in enumerate(j.get("pages", []) or []):
        if isinstance(pg.get("displayName"), str):
            refs.append(("pages[%d].displayName" % pi, pg, "displayName"))
        f = pg.get("fields") or {}
        for k in FIELD_KEYS:
            if isinstance(f.get(k), str):
                refs.append(("pages[%d].fields.%s" % (pi, k), f, k))
        for lk, subkeys in LIST_FIELDS.items():
            for ii, item in enumerate(f.get(lk, []) or []):
                if not isinstance(item, dict):
                    continue
                for sk in subkeys:
                    if isinstance(item.get(sk), str):
                        refs.append(("pages[%d].fields.%s[%d].%s" % (pi, lk, ii, sk), item, sk))
    return refs


def extract(path):
    """翻訳対象セグメントを文書順で返す: [{"uid","text"}]。uid = "<fieldpath>#<slot>"。"""
    j = json.load(open(path, encoding="utf-8-sig"))
    out = []
    for fieldpath, container, key in _field_refs(j):
        tokens = split_field(container.get(key, ""))
        slot = 0
        for kind, val in tokens:
            if kind == "seg":
                out.append({"uid": "%s#%d" % (fieldpath, slot), "text": val["text"],
                            "tags": {str(n): t for n, t in val["tags"].items()}})
                slot += 1
    return out


def apply(path, out_path, trans):
    """trans = {uid: 訳(プレースホルダ入り)} を元 JSON に適用し翻訳済み JSON を書き出す。"""
    import os
    j = json.load(open(path, encoding="utf-8-sig"))
    n_fill = 0
    for fieldpath, container, key in _field_refs(j):
        tokens = split_field(container.get(key, ""))
        per = {}
        slot = 0
        for kind, val in tokens:
            if kind == "seg":
                uid = "%s#%d" % (fieldpath, slot)
                if uid in trans and (trans[uid] or "").strip():
                    per[slot] = trans[uid]; n_fill += 1
                slot += 1
        if per:
            container[key] = rebuild_field(tokens, per)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    json.dump(j, open(out_path, "w", encoding="utf-8"),
              ensure_ascii=False, separators=(",", ":"))
    return {"filled": n_fill}


def supported_exts():
    return [".json"]
