# -*- coding: utf-8 -*-
"""Lane K2 候補棚卸し: 原文中に高頻出なのに実体化されていない語のリストを作る（決定論・LLM 不使用）。

対象: L0 投稿全文（structured.jsonl 各 post body）から
 - 片名詞らしき語（カタカナ 3〜12 / 漢字＋中点 2〜12 / 漢字 2〜6 語）を抽出
 - 篇数で集計、5 篇以上を候補化
 - 既-cover（entities 面・allusion_entities 面・topics 面・allusion 対象名・篇/作品名）を除去
出力: data/yuragi_k2_candidates.json（[{term, units, sample}] 降順）
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
SITE = W.parent / "YuragiWiki" / "content"
OUT = W / "data" / "yuragi_k2_candidates.json"

PAT_KATA = re.compile(r"[ァ-ヴーヵヶ]{3,12}")
PAT_KANJI = re.compile(r"[一-龥]{2,8}")


def jl(p: Path):
    if not p.is_file():
        return []
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if l.strip():
            try:
                r = json.loads(l)
            except Exception:
                continue
            if isinstance(r, dict) and "_meta" in r:
                continue
            out.append(r)
    return out


def main():
    covered = set()
    for sub in ("entities", "allusion_entities", "topics", "works"):
        d = SITE / sub
        if d.is_dir():
            for p in d.glob("*.md"):
                covered.add(ex.norm(p.stem))
    led = json.loads((W / "data/yuragi_allud_batches.json").read_text(encoding="utf-8"))
    runs = [b["run_dir"] for b in led["batches"] if b.get("status") == "done" and b.get("run_dir")]
    for r in runs:
        d = W / "work/yuragi/L1/runs" / r / "allusions"
        if not d.is_dir():
            continue
        for jf in d.glob("*.jsonl"):
            if jf.stem.startswith(("gate", "audit", "_")):
                continue
            for it in jl(jf):
                t = ex.norm(it.get("term", ""))
                if t:
                    covered.add(t)
    l0 = W / "work/yuragi/L0"
    latest = (l0 / "latest.txt").read_text(encoding="utf-8").strip()
    unit_rows = jl(l0 / "runs" / latest / "units.jsonl")
    per_unit_terms: dict = {}
    n = 0
    for u in unit_rows:
        uid = u["unit_id"]
        try:
            sd, meta = ex.unit_dir(uid)
        except Exception:
            continue
        rows = jl(sd / "structured.jsonl")
        c = Counter()
        for r in rows:
            body = re.sub(r"https?://\S+", " ", str(r.get("body", "")))
            body = re.sub(r"\[\[.*?\]\]", " ", body)
            for m in PAT_KATA.findall(body):
                c[m] += 1
            for m in PAT_KANJI.findall(body):
                c[m] += 1
        for t in c:
            per_unit_terms.setdefault(t, set()).add(uid)
        n += 1
        if n % 40 == 0:
            print(f"[k2] units={n}", flush=True)
    cand = []
    for t, us in per_unit_terms.items():
        if len(us) < 5:
            continue
        nt = ex.norm(t)
        if nt in covered:
            continue
        cand.append({"term": t, "units": len(us)})
    cand.sort(key=lambda x: -x["units"])
    OUT.write_text(json.dumps(cand, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[k2] units={n} covered={len(covered)} candidates(>=5篇)={len(cand)}")
    for c0 in cand[:40]:
        print(" ", c0["term"], c0["units"])


if __name__ == "__main__":
    main()
