#!/usr/bin/env python3
"""ゆらぎコーパス实体分類 — terms(count>=min) を LLM で类型分類し entities.jsonl を生成。

python scripts/classify_yuragi_entities.py [--min 5] [--workers 3]
出力: work/yuragi/L1/entities.jsonl
  {term, count, type, is_entity, note}
类型: 人物 / 种族・生物 / 組織・勢力 / 国・地域・場所 / 物品・武具 / 技・能力・方法
      / 現象・出来事 / 概念 / 作品・メタ / 非实体
※ 台帳方針: 名義統合は行わない（別名義ページ＋ link）。統合候補は note に記録のみ。
"""
import argparse
import datetime as dt
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_yuragi_l1_gen import call_llm, jl, l0_paths, unit_dirs, term_context, L1, CFG

TYPES = "人物/种族・生物/組織・勢力/国・地域・場所/物品・武具/技・能力・方法/現象・出来事/概念/作品・メタ/非实体"


def classify_batch(terms, udirs):
    parts = []
    for t in terms:
        ctx = term_context(t["term"], udirs)
        parts.append(f"### 語「{t['term']}」（登場 {t['count']} 件）\n" + "\n".join(ctx[:10]))
    prompt = (
        "『ゆらぎの神話』BBS 実況コーパスの語句を、作中实体として分類してください。\n"
        "=== 語句と出現文脈 ===\n" + "\n\n".join(parts) +
        "\n\n出力規定: 各語句について 1 行、`語: 类型|实体判定|統合候補があれば相手の語` 形式。\n"
        f"- 类型は次から 1 つ: {TYPES}\n"
        "- 实体判定 は 实体 または 非实体（実在の物・メタ用語・一般名詞だけの語は非实体）\n"
        "- 統合候補: 同一实体を指す別名義（略称・全称など）があれば相手の語を記録するだけ（統合はしない）\n"
        "- 判断は提示文脈と語の形から。行頭に番号を付けない。余文なし。")
    resp = call_llm(prompt, max_tokens=3000)
    out = {}
    for line in resp.splitlines():
        line = line.strip().lstrip("0123456789. 、)（(")
        m = line.split(":", 1) if ":" in line else line.split("：", 1)
        if len(m) != 2:
            continue
        term = m[0].strip().strip("「」\"'")
        rest = m[1].split("|")
        if term and len(rest) >= 2:
            out[term] = {"type": rest[0].strip(), "is_entity": rest[1].strip() == "实体",
                         "note": rest[2].strip() if len(rest) > 2 else ""}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=5)
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    latest, sp = l0_paths()
    udirs = unit_dirs(latest)
    terms = [r for r in jl(sp / "terms.jsonl") if r["count"] >= a.min]
    terms.sort(key=lambda r: -r["count"])
    print(f"terms>= {a.min}: {len(terms)}")
    batches = [terms[i:i + 10] for i in range(0, len(terms), 10)]
    results = {}
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(classify_batch, b, udirs) for b in batches]
        for f in futs:
            for k, v in f.result().items():
                results[k] = v
    rows = []
    for t in terms:
        r = results.get(t["term"])
        if r is None:
            r = {"type": "概念", "is_entity": True, "note": "", "unclassified": True}
        rows.append({"term": t["term"], "count": t["count"], **r,
                     "classified_by": CFG["model"], "ts": dt.datetime.now().isoformat()})
    out = L1 / "entities.jsonl"
    out.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
    ent = sum(1 for r in rows if r["is_entity"])
    print(json.dumps({"total": len(rows), "entities": ent, "non_entities": len(rows) - ent,
                      "unclassified": sum(1 for r in rows if r.get("unclassified"))}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
