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

def norm(s):
    return re.sub(r"[\s\u3000,、,]+", "", s)

def trim_quote(q):
    if len(q) <= 100:
        return q
    cut = q[:101]
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
    only = set(sys.argv[1:])
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    import json
    units = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        units.setdefault(u["unit_id"], u)
    run = L1 / "runs" / "20261117T2115_l1u" / "units"
    fixed = 0
    for p in sorted(run.glob("*.md")):
        uid = p.stem
        if only and uid not in only:
            continue
        art = p.read_text(encoding="utf-8")
        m = re.search(r"(##\s*注目投稿.*?)(?=\n##|\Z)", art, re.S)
        if not m:
            continue
        sec = m.group(1)
        body = norm("\n".join(x["body"] for x in jl(unit_dir(units[uid]) / "structured.jsonl")))
        lines = sec.split("\n")
        out_lines = []
        for line in lines:
            mm = re.search(r"「([^」]+)」", line)
            if not mm:
                out_lines.append(line)
                continue
            q = mm.group(1)
            q = trim_quote(q)
            if norm(q) in body:
                out_lines.append(line[:mm.start(1)] + q + line[mm.end(1):])
                continue
            sub = lcs_sub(norm(q), body)
            if sub and len(sub) >= 0.6 * len(norm(q)):
                out_lines.append(line[:mm.start(1)] + sub + line[mm.end(1):])
            # LCS 60% 未満 → 引用付き行を削除
        new = "\n".join(out_lines)
        if new != sec:
            p.write_text(art[:m.start(1)] + new + art[m.end(1):], encoding="utf-8")
            fixed += 1
    print(json.dumps({"fixed_articles": fixed}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    sys.exit(main())
