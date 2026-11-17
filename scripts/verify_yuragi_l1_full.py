#!/usr/bin/env python3
"""制約なし版 L1 の機械検証 — 決定論組立を再構成し、収録ページと完全一致するか。

builder (build_yuragi_l1_full.py) と同一の「## スレッド原文」節を再構成し、
ページ収録節とバイト一致で照合する（SHA・改行変換に依存しない最も強い検証）。
"""
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
    rid = max(p.name for p in (L1 / "runs").iterdir() if p.is_dir() and p.name.endswith("_l1full"))
    run = L1 / "runs" / rid
    l0_latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units, seen = [], set()
    for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
        if u["unit_id"] not in seen:
            seen.add(u["unit_id"])
            units.append(u)
    issues, n = [], 0
    for u in units:
        uid = u["unit_id"]
        d = (RAW / u["raw_path"].rsplit("/", 1)[0] if u["source"] == "jbbs"
             else RAW / "mixi/373088" / u["title"] if u["source"] == "mixi"
             else RAW / "hatena_flicker")
        posts = jl(d / "structured.jsonl")
        sec = ["\n\n## スレッド原文（全文・制約なし版）\n",
               "\n> 原文の著作権は各投稿者に帰属します。出典: YuragiWiki raw（" + u["url"] + "）\n"]
        for p in posts:
            sec.append(f"\n**{p['post_no']}** {p['author']} {p.get('date_iso') or '（日付なし）'}\n\n"
                       + p["body"] + "\n")
        expected = "".join(sec)
        md = run / "units" / f"{uid}.md"
        if not md.exists():
            issues.append(f"{uid}:PAGE_MISSING")
            continue
        t = rd(md)
        i = t.find("## スレッド原文（全文・制約なし版）")
        if i < 0:
            issues.append(f"{uid}:SECTION_MISSING")
            continue
        got = t[i - 2:] if t[i - 2:i] == "\n\n" else t[i:]
        if got != expected:
            issues.append(f"{uid}:SECTION_DIFF len {len(got)}!={len(expected)}")
            continue
        n += 1
    print(json.dumps({"rid": rid, "pages_ok": n, "units": len(units),
                      "issues": len(issues), "sample": issues[:8]}, ensure_ascii=False))
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())
