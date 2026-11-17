#!/usr/bin/env python3
"""Yuragi L0 検索システム — 語句・作者・日付・全文・要約検索を ref 付きで返す。

使い方:
  python scripts/search_yuragi.py term  <語>[ <語>..]    # 語句索引（完全一致→部分一致）、AND 可
  python scripts/search_yuragi.py author <名>            # 作者の投稿一覧
  python scripts/search_yuragi.py date   <YYYY-MM-DD> [<YYYY-MM-DD>]  # 期間
  python scripts/search_yuragi.py grep   <regex> [--ctx N] [--unit U]  # 全文（③ body）
  python scripts/search_yuragi.py chain  <kw>           # ④ LLM 要約キーワード
  python scripts/search_yuragi.py unit   <kw>           # 篇タイトル
  共通: --json (JSONL 出力)  --max N (ref 上限・既定 50)
出力の ref（YJ-T031:1245）/ chain_id は scripts/read_yuragi.py で本文・文脈を復元する。
"""
import json
import re
import sys
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            continue
        out.append(r)
    return out

def paths():
    sdir = None
    for p in sorted((L0 / "runs").iterdir()):
        if p.is_dir() and p.name.endswith("_l0si") and (p / "search").exists():
            sdir = p
    if sdir is None:
        raise SystemExit("search 索引 run なし")
    return sdir / "search"

def show(refs, meta_map=None, mx=50, as_json=False):
    for i, r in enumerate(refs[:mx]):
        if as_json:
            print(json.dumps({"ref": r}, ensure_ascii=False))
        else:
            extra = f"  {meta_map[r]}" if meta_map and r in meta_map else ""
            print(r + extra)
    if len(refs) > mx:
        print(f"… 計 {len(refs)} 件（--max 増設可）")

def main():
    args = [a for a in sys.argv[1:]]
    if not args:
        print(__doc__)
        return 0
    cmd = args[0]
    as_json = "--json" in args
    mx = int(args[args.index("--max") + 1]) if "--max" in args else 50
    sp = paths()

    if cmd == "term" and len(args) >= 2:
        terms = {r["term"]: r for r in jl(sp / "terms.jsonl")}
        words = [a for a in args[1:] if not a.startswith("--")]
        cand = set(terms)
        for w in words:
            exact = {t for t in terms if t == w}
            sub = {t for t in terms if w in t}
            cand &= (exact | sub) if (exact | sub) else set()
        rows = sorted((terms[t] for t in cand), key=lambda r: -r["count"])
        for r in rows[:mx]:
            if as_json:
                print(json.dumps(r, ensure_ascii=False))
            else:
                print(f"{r['term']}\t{r['count']} 件\tunits: {','.join(r['units_touched'][:12])}")
                print("  refs: " + " ".join(r["refs"][:20]))
        print(f"# 語句 {len(rows)} 件ヒット / 索引 {len(terms)} 語")

    elif cmd == "author" and len(args) >= 2:
        w = args[1]
        for r in jl(sp / "by-author.jsonl"):
            if r["author"] == w or w in r["author"]:
                print(f"# {r['author']}: {r['n']} 件")
                show(r["refs"], mx=mx, as_json=as_json)

    elif cmd == "date" and len(args) >= 2:
        import datetime as dt
        def ep(s):
            return dt.datetime.fromisoformat(s + "T00:00:00+09:00").timestamp()
        a = ep(args[1])
        b = ep(args[2]) + 86400 if len(args) > 2 and not args[2].startswith("--") else a + 86400
        rows = [r["ref"] for r in jl(sp / "by-date.jsonl") if r.get("epoch") and a <= r["epoch"] < b]
        print(f"# 期間 {args[1]}.. → {len(rows)} 件")
        show(rows, mx=mx, as_json=as_json)

    elif cmd == "grep" and len(args) >= 2:
        pat = re.compile(args[1])
        unit_filter = args[args.index("--unit") + 1] if "--unit" in args else None
        # unit dir 解決（台帳 units.jsonl）→ ③ body を直接読む
        latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
        udir = {}
        for u in jl(L0 / "runs" / latest / "units.jsonl"):
            uid = u["unit_id"]
            d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
                 else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
                 else RAW / "hatena_flicker")
            udir[uid] = d
        cache = {}
        hits = []
        for uid, d in sorted(udir.items()):
            if unit_filter and uid != unit_filter:
                continue
            for p in jl(d / "structured.jsonl"):
                body = p["body"]
                for mm in pat.finditer(body):
                    hits.append((p["ref"], body[max(0, mm.start()-40):mm.end()+40].replace("\n", "⏎")))
                    break
        print(f"# 全文ヒット {len(hits)} 件")
        for ref, ctx in hits[:mx]:
            print(f"{ref}\t{ctx}" if not as_json else json.dumps({"ref": ref, "ctx": ctx}, ensure_ascii=False))

    elif cmd == "chain" and len(args) >= 2:
        kw = args[1]
        latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
        n = 0
        for u in jl(L0 / "runs" / latest / "units.jsonl"):
            uid = u["unit_id"]
            d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
                 else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
                 else RAW / "hatena_flicker")
            for c in jl(d / "chains.jsonl"):
                s = c.get("summary", "")
                if kw in s or kw in " ".join(c.get("topics", [])):
                    n += 1
                    if n <= mx:
                        print(f"{c['chain_id']}\t{s}" if not as_json
                              else json.dumps(c, ensure_ascii=False))
        print(f"# 要約ヒット {n} 件")

    elif cmd == "unit" and len(args) >= 2:
        kw = args[1]
        for r in jl(sp / "posts.jsonl"):
            if kw in r["title"]:
                print(json.dumps(r, ensure_ascii=False)) if as_json else None
        seen = set()
        for r in jl(sp / "posts.jsonl"):
            if kw in r["title"] and r["unit_id"] not in seen:
                seen.add(r["unit_id"])
                print(f"{r['unit_id']}\t{r['title']}\t{r['url']}")
    else:
        raise SystemExit("usage: term/author/date/grep/chain/unit ...  [--json] [--max N]")
    return 0

if __name__ == "__main__":
    sys.exit(main())
