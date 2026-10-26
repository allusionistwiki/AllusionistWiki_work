"""S4V3: v3 裁定の台帳適用 — 実体有効性・親子構造。

Usage: python scripts/apply_l2_v3.py <run_id>
Input : runs/<id>/entities.json（現台帳）+ adjudications_v3.jsonl + v3-inventory.jsonl
Output: entities.json 更新（schema l2-entities/3: parent/children/status 追加）
        v3-applied.json（適用内訳）

category 適用:
 standalone → 新規实体（kind・first_seen・l1_refs は inventory から）
 aspect_of  → 新規实体 + parent 付与（親の children にも登録）
 generic    → 新規实体に entity_status=generic（相関索引から除外表示）
 alias_of   → target 实体の aliases へ追加
 needs      → 新規实体 entity_status=needs（kind 未確定）
冪等: 同一 norm の再適用はスキップ（既存 id / v3-applied 記録）。
"""
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS, norm_key

RUN = sys.argv[1]
OUT = L2_RUNS / RUN
PREF = {"character": "char", "item": "item", "terminology": "term",
        "organization": "org", "location": "loc", "creature": "creature",
        "event": "event", "relationship": "rel", "motif": "motif",
        "phrase": "phrase", "": "term"}


def jl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    data = json.loads((OUT / "entities.json").read_text(encoding="utf-8"))
    ents = data["entities"]
    by_norm = {}
    for e in ents:
        by_norm[norm_key(e["canonical"])] = e
        for a in e.get("aliases", []):
            by_norm.setdefault(norm_key(a), e)
    inv = {r["norm"]: r for r in jl(OUT / "v3-inventory.jsonl")}
    verdicts = {}
    for r in jl(OUT / "adjudications_v3.jsonl"):
        for v in r.get("verdicts", []):
            verdicts[v["norm"]] = v

    applied = {"standalone": 0, "aspect_of": 0, "generic": 0, "alias_of": 0,
               "needs": 0, "skip_existing": 0}
    for nk, v in verdicts.items():
        row = inv.get(nk, {})
        cat = v.get("category")
        surfaces = row.get("surfaces", [])
        disp = max([nk] + surfaces, key=len) if surfaces else nk
        exist = by_norm.get(nk)
        if cat == "alias_of":
            tgt = by_norm.get(norm_key(v.get("target") or ""))
            if tgt and exist is tgt:
                applied["skip_existing"] += 1
                continue
            if tgt:
                if disp not in tgt["aliases"]:
                    tgt["aliases"].append(disp)
                applied["alias_of"] += 1
            continue
        if exist:
            if cat == "aspect_of":
                par = by_norm.get(norm_key(v.get("parent") or ""))
                if par and par is not exist:
                    exist["parent"] = {"id": par["id"], "relation": "aspect"}
                    par.setdefault("children", []).append(
                        {"id": exist["id"], "relation": "aspect"})
                    applied["aspect_of"] += 1
                continue
            if cat == "generic":
                exist["entity_status"] = "generic"
                applied["generic"] += 1
                continue
            applied["skip_existing"] += 1
            continue
        kind = v.get("kind") or ""
        if kind not in PREF:
            kind = row.get("page_subtype") or ""
            kind = kind if kind in PREF else "terminology"
        et = row.get("entity_type_votes", {})
        if not v.get("kind") and et:
            top = max(et.items(), key=lambda x: x[1])[0]
            kind = top if top in PREF else kind
        eid = "E_%s_%s" % (PREF.get(kind, "term"), disp)
        if any(e["id"] == eid for e in ents):
            eid = eid + "_v3"
        new = {
            "id": eid, "canonical": disp,
            "aliases": sorted(set(s for s in surfaces if norm_key(s) == nk and s != disp)),
            "kind": kind,
            "kind_confidence": "裁定済" if v.get("kind") else "機械",
            "merge_evidence": v.get("confidence", "要検証"),
            "entity_status": {"standalone": "active", "aspect_of": "active",
                              "generic": "generic", "needs": "needs"}[cat],
            "l1_refs": [{"run": RUN, "ep": q.get("ep"), "quote": q.get("q")}
                        for q in row.get("quotes", [])][:3],
        }
        eps = row.get("episodes", [])
        if eps:
            new["first_seen"] = {"ep": eps[0]}
        ents.append(new)
        by_norm[nk] = new
        if cat == "aspect_of":
            par = by_norm.get(norm_key(v.get("parent") or ""))
            if par and par is not new:
                new["parent"] = {"id": par["id"], "relation": "aspect"}
                par.setdefault("children", []).append(
                    {"id": new["id"], "relation": "aspect"})
        applied[cat] += 1

    data["schema"] = "l2-entities/3"
    data["v3_applied"] = applied
    (OUT / "entities.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "v3-applied.json").write_text(json.dumps(
        {**applied, "at": datetime.now().isoformat(),
         "entities_total": len(ents)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("applied:", json.dumps(applied, ensure_ascii=False))
    print("entities_total=%d" % len(ents))
    print("=== L2 APPLY V3 DONE ===")


if __name__ == "__main__":
    main()
