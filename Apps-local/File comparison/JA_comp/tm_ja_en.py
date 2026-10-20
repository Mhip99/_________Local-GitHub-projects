# -*- coding: utf-8 -*-
"""TM(TMX) から JA⇄EN 双方向の照合索引を作る（ストリーミング解析＋pickleキャッシュ）。

  * JA→EN: 日本語セグメント(正規化)→ 英語原文(surface)。日本語本文から原文英語を引く
           （ファイル名が異なる記事の内容照合に使用）。
  * EN→JA: 英語セグメント(正規化)→ 日本語訳(正規化)。英語本文の各文の訳文を引き、対象
           JA本文に含まれるかで「カバレッジ率=Match rate」を測る。

どちらも exact マップ＋文字トライグラム転置索引(あいまい照合)を持つ。指紋=TMX の
パス+サイズ+更新時刻。FORMAT_VERSION が変われば自動再構築。
"""
import os, re, io, sys, time, json, pickle, hashlib
import xml.etree.ElementTree as ET
from collections import Counter

FORMAT_VERSION = "jaen-enja-2"
XTAG = re.compile(r"<[^>]+>")
TRICAP = 8000

def norm_ja(s):
    s = XTAG.sub("", s or "")
    s = re.sub(r"\s+", "", s)
    return s.strip().lower()

def norm_en(s):
    s = XTAG.sub(" ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

def key_en(s):
    return norm_en(s).lower()

def trigrams(s):
    if len(s) >= 3:
        return set(s[i:i+3] for i in range(len(s) - 2))
    return {s} if s else set()


class TMIndex:
    __slots__ = ("ja_exact", "ja_keys", "en_surface", "ja_inv",
                 "en_exact", "en_keys", "ja_surface", "en_inv", "meta")
    def __init__(self):
        self.ja_exact = {}      # norm_ja -> en surface(norm_en)
        self.ja_keys = []       # id -> norm_ja
        self.en_surface = []    # id -> en surface (ja_keys と対応)
        self.ja_inv = {}        # ja trigram -> [ja id]
        self.en_exact = {}      # key_en -> ja ref(norm_ja)
        self.en_keys = []       # id -> key_en
        self.ja_surface = []    # id -> ja ref(norm_ja) (en_keys と対応)
        self.en_inv = {}        # en trigram -> [en id]
        self.meta = {}
TMIndex.__module__ = "tm_ja_en"


def _index_tmx(idx, path, log):
    strip = lambda t: t.split("}")[-1]
    n = 0
    for ev, el in ET.iterparse(path, events=("end",)):
        if strip(el.tag) != "tu":
            continue
        n += 1
        en = ja = None
        for ch in el:
            if strip(ch.tag) == "tuv":
                lang = ch.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or ch.attrib.get("lang") or ""
                seg = "".join("".join(s.itertext()) for s in ch if strip(s.tag) == "seg")
                if lang.lower().startswith("en"):
                    en = seg
                elif lang.lower().startswith("ja"):
                    ja = seg
        if en is not None and ja is not None:
            kj = norm_ja(ja); ens = norm_en(en)
            # JA -> EN
            if kj and len(kj) >= 4 and kj not in idx.ja_exact:
                idx.ja_exact[kj] = ens
                jid = len(idx.ja_keys); idx.ja_keys.append(kj); idx.en_surface.append(ens)
                for tg in trigrams(kj):
                    lst = idx.ja_inv.setdefault(tg, [])
                    if len(lst) < TRICAP:
                        lst.append(jid)
            # EN -> JA
            ke = key_en(en)
            if ke and len(ke) >= 6 and kj and ke not in idx.en_exact:
                idx.en_exact[ke] = kj
                eid = len(idx.en_keys); idx.en_keys.append(ke); idx.ja_surface.append(kj)
                for tg in trigrams(ke):
                    lst = idx.en_inv.setdefault(tg, [])
                    if len(lst) < TRICAP:
                        lst.append(eid)
        el.clear()
        if n % 100000 == 0:
            log("  TU", n, "| JA keys", len(idx.ja_keys), "| EN keys", len(idx.en_keys))
    log("  done TU", n, "| JA keys", len(idx.ja_keys), "| EN keys", len(idx.en_keys))


def _fingerprint(paths):
    parts = [FORMAT_VERSION]
    for p in paths:
        st = os.stat(p)
        parts.append("%s|%d|%d" % (os.path.abspath(p).lower(), st.st_size, st.st_mtime_ns))
    return hashlib.md5("\n".join(parts).encode("utf-8")).hexdigest()[:16]


def build(paths, log=print):
    idx = TMIndex(); t0 = time.time()
    for p in paths:
        log("indexing TMX (JA<->EN):", os.path.basename(p))
        _index_tmx(idx, p, log)
    idx.meta = {"version": FORMAT_VERSION, "built": time.strftime("%Y-%m-%d %H:%M:%S"),
                "seconds": round(time.time() - t0, 1),
                "ja_keys": len(idx.ja_keys), "en_keys": len(idx.en_keys),
                "tmx": [os.path.basename(p) for p in paths]}
    log("TMX done. JA %d / EN %d keys | %.1fs" % (len(idx.ja_keys), len(idx.en_keys), idx.meta["seconds"]))
    return idx


def load_or_build(paths, cache_dir, rebuild=False, log=print):
    fp = _fingerprint(paths)
    os.makedirs(cache_dir, exist_ok=True)
    pkl = os.path.join(cache_dir, "tmidx_%s.pkl" % fp)
    if os.path.exists(pkl) and not rebuild:
        try:
            with open(pkl, "rb") as f:
                idx = pickle.load(f)
            if getattr(idx, "meta", {}).get("version") == FORMAT_VERSION:
                log("TM cache HIT: %s | JA %d / EN %d keys" % (os.path.basename(pkl), len(idx.ja_keys), len(idx.en_keys)))
                return idx
        except Exception as e:
            log("TM cache 読込失敗(%s); 再構築" % e)
    idx = build(paths, log=log)
    try:
        with open(pkl, "wb") as f:
            pickle.dump(idx, f, protocol=pickle.HIGHEST_PROTOCOL)
        with open(os.path.join(cache_dir, "tmidx_%s.json" % fp), "w", encoding="utf-8") as f:
            json.dump({"fingerprint": fp, **idx.meta}, f, ensure_ascii=False, indent=1)
        log("TM cache SAVED: %s" % os.path.basename(pkl))
    except Exception as e:
        log("WARNING: TM cache 保存失敗(%s)" % e)
    return idx


def lookup(idx, ja_text, min_ratio=0.6, cand_cap=60):
    """JA テキスト→(EN surface, ratio)。exact 優先、無ければトライグラム類似で最良。"""
    k = norm_ja(ja_text)
    if not k:
        return None, 0.0
    if k in idx.ja_exact:
        return idx.ja_exact[k], 1.0
    q = trigrams(k)
    if not q:
        return None, 0.0
    cnt = Counter()
    for tg in q:
        for kid in idx.ja_inv.get(tg, ()):
            cnt[kid] += 1
    best, bestr = None, 0.0
    for kid, _ in cnt.most_common(cand_cap):
        qk = trigrams(idx.ja_keys[kid])
        r = len(q & qk) / len(q | qk) if (q | qk) else 0.0
        if r > bestr:
            bestr, best = r, idx.en_surface[kid]
    if bestr >= min_ratio:
        return best, round(bestr, 3)
    return None, round(bestr, 3)


def lookup_en2ja_exact(idx, en_text):
    """EN テキスト→ JA ref(norm_ja)。exact 一致のみ(高速)。無ければ None。
    大量の文をカバレッジ判定する用途(あいまい照合は候補が膨大で遅いため使わない)。"""
    return idx.en_exact.get(key_en(en_text))


def lookup_en2ja(idx, en_text, min_ratio=0.6, cand_cap=60):
    """EN テキスト→(JA ref[norm_ja], ratio)。exact 優先、無ければトライグラム類似で最良。"""
    k = key_en(en_text)
    if not k:
        return None, 0.0
    if k in idx.en_exact:
        return idx.en_exact[k], 1.0
    q = trigrams(k)
    if not q:
        return None, 0.0
    cnt = Counter()
    for tg in q:
        for kid in idx.en_inv.get(tg, ()):
            cnt[kid] += 1
    best, bestr = None, 0.0
    for kid, _ in cnt.most_common(cand_cap):
        qk = trigrams(idx.en_keys[kid])
        r = len(q & qk) / len(q | qk) if (q | qk) else 0.0
        if r > bestr:
            bestr, best = r, idx.ja_surface[kid]
    if bestr >= min_ratio:
        return best, round(bestr, 3)
    return None, round(bestr, 3)


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tmx", required=True, nargs="+")
    ap.add_argument("--cache-dir", required=True)
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    idx = load_or_build(a.tmx, a.cache_dir, rebuild=a.rebuild)
    print("ready. JA keys:", len(idx.ja_keys), "| EN keys:", len(idx.en_keys))
