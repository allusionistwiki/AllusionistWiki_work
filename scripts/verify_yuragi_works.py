#!/usr/bin/env python3
"""works ページの機械検証 — 収録投稿 body が structured.jsonl とバイト一致か、全創作群が収容されているか。"""
import json
import sys
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"

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

def main():
    rid = max(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1works"))
    run = L1 / "runs" / rid
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units = {}
    for u in jl(L0 / "runs" / latest / "units.jsonl"):
        units.setdefault(u["unit_id"], u)
    unit_data = {}
    for uid, u in units.items():
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        unit_data[uid] = {
            "by_no": {p["post_no"]: p for p in jl(d / "structured.jsonl")},
            "chains": {c["chain_id"]: c for c in jl(d / "chains.jsonl")},
        }
    ledger = [json.loads(l) for l in (L1 / "works.jsonl").read_bytes().decode("utf-8").splitlines() if l.strip()]
    cre = [r for r in ledger if r.get("creative")]
    # ページ内テキスト收集（全 works ページを 1 つの文字列に）
    corpus = "\n".join(rd(p) for p in sorted((run / "works").glob("*.md")))
    issues = []
    posts_ok = 0
    chains_ok = 0
    for r in cre:
        uid = r["uid"]
        ud = unit_data.get(uid)
        if not ud:
            issues.append(f"{r['chain_id']}:UNIT_MISSING")
            continue
        c = ud["chains"].get(r["chain_id"])
        nos = (c.get("post_nos") if c and c.get("post_nos")
               else list(range(r["post_range"][0], r["post_range"][1] + 1)))
        all_ok = True
        for n in nos:
            p = ud["by_no"].get(n)
            if not p:
                continue
            if f"**{n}** {p.get('author','')} {p.get('date_iso') or ''}" in corpus and p["body"] in corpus:
                posts_ok += 1
            else:
                all_ok = False
                issues.append(f"{r['chain_id']}:post{n}:BODY_MISSING")
        if all_ok:
            chains_ok += 1
    print(json.dumps({"rid": rid, "creative_chains": len(cre), "chains_ok": chains_ok,
                      "posts_ok": posts_ok, "issues": len(issues), "sample": issues[:6]},
                     ensure_ascii=False))
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())
