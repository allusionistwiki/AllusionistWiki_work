#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""standalone linkfix: YuragiWiki 解析面の壊リンクを remap/テキスト化で 0 に収束。
publish 末尾の linkfix 網と同ロジック（供給再生成後の site 実ファイルに対する収束作業）。"""
import re
import sys
import unicodedata as ud
from pathlib import Path

CONTENT = Path("C:/Users/d5dx/Downloads/Code/YuragiWiki/content")
SCAN_DIRS = ("entities", "entities_map", "allusion_entities")

def build():
    folders = {}
    for d in CONTENT.iterdir():
        if d.is_dir():
            folders[d.name] = {q.stem: q for q in d.glob("*.md")}
    folders["."] = {q.stem: q for q in CONTENT.glob("*.md")}
    # グリフ変異ペア検出（ハミング距離1の CJK 1字差 stem 組）
    all_stems = [s for mp in folders.values() for s in mp]
    variant = {}
    by_key = {}
    for s in all_stems:
        k0 = ud.normalize("NFKC", s).lower()
        kk = k0.replace("_", "")
        by_key.setdefault((len(k0), kk[:2] + kk[-2:]), []).append(s)
    for grp in by_key.values():
        for i in range(len(grp)):
            for j in range(i + 1, len(grp)):
                a, b = grp[i], grp[j]
                na, nb = ud.normalize("NFKC", a).lower(), ud.normalize("NFKC", b).lower()
                if len(na) != len(nb):
                    continue
                diff = [(x, y) for x, y in zip(na, nb) if x != y]
                if len(diff) == 1 and all(ord(x) > 0x2000 for x, y in diff):
                    x, y = diff[0]
                    cx = sum(1 for s2 in all_stems if x in ud.normalize("NFKC", s2).lower())
                    cy = sum(1 for s2 in all_stems if y in ud.normalize("NFKC", s2).lower())
                    if cx >= cy:
                        variant[y] = x
                    else:
                        variant[x] = y
    def nk(s):
        s = ud.normalize("NFKC", s)
        for vc, vt in variant.items():
            if vc in s:
                s = s.replace(vc, vt)
        for ch in ("・", "：", ":", "/", "?", "!", "　", "\\", "＆", "＃", "％", "_", "ー"):
            s = s.replace(ch, "")
        return s.lower()
    idx = {f: {nk(k): k for k in d} for f, d in folders.items()}
    return folders, idx, nk

def main():
    folders, idx, nk = build()
    fixed = textified = 0
    targets = []
    for d in SCAN_DIRS:
        targets.extend((CONTENT / d).glob("*.md"))
    targets.extend(CONTENT.glob("*.md"))
    for p in targets:
        t = p.read_text(encoding="utf-8", errors="replace")
        if "[[" not in t:
            continue
        def rep(mo):
            nonlocal fixed, textified
            if mo.group(2).startswith("#"):
                return mo.group(0)
            tgt = mo.group(2).split("#")[0].strip()
            pipe = mo.group(3) or ""
            parts = tgt.split("/", 1)
            fld = "." if len(parts) == 1 else parts[0]
            base = parts[-1]
            dmap = folders.get(fld)
            if dmap is None:
                return mo.group(1)
            if base in dmap:
                return mo.group(0)
            lk = nk(base)
            ik = idx.get(fld, {}).get(lk)
            if ik is None and lk:
                cand = [k for k in idx.get(fld, {}) if lk in k]
                if len(cand) == 1:
                    ik = cand[0]
                elif not cand and len(lk) >= 4:
                    pref = lk[: len(lk) - 1]
                    cand = [k for k in idx.get(fld, {}) if k.startswith(pref)]
                    if len(cand) == 1:
                        ik = cand[0]
            if ik:
                fixed += 1
                pfx = "" if fld == "." else fld + "/"
                return f"{mo.group(1)}{pfx}{ik}{pipe}]]"
            if fld != ".":
                lk2 = lk
                for f2, d2 in idx.items():
                    if f2 == fld:
                        continue
                    ik2 = d2.get(lk2)
                    if ik2 is None and lk2:
                        cd2 = [k for k in d2 if lk2 in k]
                        if len(cd2) == 1:
                            ik2 = cd2[0]
                    if ik2:
                        fixed += 1
                        pfx2 = "" if f2 == "." else f2 + "/"
                        return f"{mo.group(1)}{pfx2}{ik2}{pipe}]]"
                textified += 1
                return pipe[1:] if pipe else base
            return mo.group(0)
        t2 = re.sub(r"(\[\[)([^\]|]+)(\|[^\]]*)?\]\]", rep, t)
        if t2 != t:
            p.write_text(t2, encoding="utf-8", newline="\n")
    print(f"[linkfix-standalone] remapped={fixed} textified={textified}")


    # 2026-11-23 恒久安全網: 書き出し後の改行正規化（CRLF・単独 CR → LF）
    # Quartz の block HTML comment 内で \r\r\n が入ると html プロセッサが null.data で落ちる
    nlfix = 0
    for pn in CONTENT.rglob("*.md"):
        b = pn.read_bytes()
        if b"\r" in b:
            pn.write_bytes(b.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
            nlfix += 1
    print(f"[nlfix-standalone] crlf_normalized={nlfix}")


if __name__ == "__main__":
    main()
