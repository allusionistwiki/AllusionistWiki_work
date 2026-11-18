#!/usr/bin/env python3
"""L1 篇記事の引用を機械修復する — 注目投稿欄の引用をコーパス原文の正確な部分文字列へ。

1. 100 字超引用 → 文境界（。！？…）で 100 字内の文に短縮（境界なしは 100 字 cut）。
2. 原文に存在しない引用（改変・合成） → 原文との最長共通部分文字列へ置換（LCS ≥ 60%）。
   LCS 60% 未満は引用付き項目行を削除。
用法: python scripts/fix_yuragi_l1_quotes.py [unit_id ...]  (省略時は全記事)
"""
import re
import sys
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L1 = W / "work" / "yuragi" / "L1"
L0 = W / "work" / "yuragi" / "L0"

def jl(p: Path):
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if not l.strip():
            continue
        import json
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            continue
        out.append(r)
    return out

def unit_dir(u):
    if u["source"] == "jbbs":
        return RAW / u["raw_path"].rsplit("/", 1)[0]
    if u["source"] == "mixi":
        return RAW / "mixi/373088" / u["title"]
    return RAW / "hatena_flicker"

import unicodedata
QUOTE_RE = re.compile(r"「((?:[^「」]|「[^」]*」)+)」")

def norm(s):
    return re.sub(r"[\s\u3000,、,]+", "", unicodedata.normalize("NFKC", s))

def trim_quote(q):
    if len(q) <= 100:
        return q
    cut = q[:100]
    i = max(cut.rfind("。"), cut.rfind("！"), cut.rfind("？"), cut.rfind("…"))
    return cut[:i+1] if i >= 30 else cut[:100]

def lcs_sub(a: str, b: str):
    """a (引用) と b (原文) の最長共通部分文字列。"""
    n, m = len(a), len(b)
    if n == 0 or m == 0:
        return ""
    best, end_i = 0, 0
    prev = [0] * (m + 1)
    for i in range(1, n + 1):
        cur = [0] * (m + 1)
        for j in range(1, m + 1):
            if a[i-1] == b[j-1]:
                cur[j] = prev[j-1] + 1
                if cur[j] > best:
                    best, end_i = cur[j], i
        prev = cur
    return a[end_i - best: end_i]

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", default="units", choices=["units", "topics", "authors", "entities"])
    ap.add_argument("--run-dir", default=None)
    ap.add_argument("only", nargs="*")
    a = ap.parse_args()
    sc_dir = {"units": "units", "topics": "topics", "authors": "authors", "entities": "entities"}[a.scope]
    suffix = {"units": "_l1u", "topics": "_l1tp", "authors": "_l1au", "entities": "_l1en"}[a.scope]
    run = max(p for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith(suffix))
    run = L1 / "runs" / (a.run_dir or run.name)
    only = set(a.only)
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    import json
    units = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        units.setdefault(u["unit_id"], u)
    # 全文コーパス（topics/authors 用・1 回構築）
    global_body = ""
    if a.scope != "units":
        parts = []
        for uid, u in units.items():
            d = unit_dir(u)
            parts.append("\n".join(x["body"] for x in jl(d / "structured.jsonl")))
        global_body = norm("\n".join(parts))
    fixed = 0
    units_norm = {}
    if a.scope != "units":
        for uid, u in units.items():
            d = unit_dir(u)
            units_norm[uid] = norm("\n".join(x["body"] for x in jl(d / "structured.jsonl")))
    for p in sorted((run / sc_dir).glob("*.md")):
        uid = p.stem
        if only and uid not in only:
            continue
        art = p.read_bytes().decode("utf-8", "replace")
        m = re.search(r"(##\s*注目投稿.*?)(?=\n##|\Z)", art, re.S)
        if not m:
            continue
        sec = m.group(1)
        if a.scope == "units":
            body = norm("\n".join(x["body"] for x in jl(unit_dir(units[uid]) / "structured.jsonl")))
            targets = [body]
        else:
            body = global_body
            targets = None  # unit 単位 probe
        # 引用が複数行にまたがるため sec 全体で QUOTE_RE 一括処理する
        def fix_q(mm):
            q = trim_quote(mm.group(1))
            qn = norm(q)
            if qn in body:
                return q
            probe = qn[:20]
            tset = [b for b in units_norm.values() if probe and probe in b] if targets is None else targets
            if not tset:
                tset = list(units_norm.values()) if targets is None else targets
            for tb in tset:
                sub = lcs_sub(qn, tb)
                if sub and len(sub) >= 0.6 * len(qn):
                    return sub
            return "（引用不採用）"
        new = QUOTE_RE.sub(fix_q, sec)
        if new != sec:
            p.write_bytes((art[:m.start(1)] + new + art[m.end(1):]).encode("utf-8"))
            fixed += 1
    print(json.dumps({"fixed_articles": fixed, "run": run.name}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
