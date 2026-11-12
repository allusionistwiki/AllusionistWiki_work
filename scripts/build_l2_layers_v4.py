#!/usr/bin/env python3
"""L2 再設計 v4: v10 台帳を 实体/呼称/役割/語彙 の 4 層ファイルへ分割する。
用法: python scripts/build_l2_layers_v4.py <base_run_id> <out_run_id>"""
import json
import sys
from datetime import datetime
from pathlib import Path

L2_RUNS = Path("C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/allusionist_v2/L2/runs")
BASE, OUT = sys.argv[1], sys.argv[2]

ENTITY_KINDS = {"character", "organization", "location", "creature", "item"}
CONCEPT_KINDS = {"terminology", "motif", "phrase", "event"}


def main():
    d = json.loads((L2_RUNS / BASE / "entities.json").read_text(encoding="utf-8"))
    ents = d["entities"]

    entities, names, roles, concepts = [], [], [], []

    # 語り手 役割縁（本体は merged 来歴として entities に残る）
    roles.append({
        "entity_id": "E_char_アキラ",
        "role": "narrator",
        "scope": "全編（一人称語り）",
        "confidence": "明言",
        "evidence": "ch00351¶4『語り手とは神なのか』は主人公そのものへのメタ問い; ch00018 品森晶（シナモリアキラ）同一性述語",
    })

    for e in ents:
        kind = e.get("kind", "")
        rec = {k: v for k, v in e.items() if k != "aliases"}
        alias_rows = []
        for a in e.get("aliases", []):
            s = a.get("name") or a.get("string")
            if not s:
                continue
            alias_rows.append({
                "name": s,
                "entity_id": e["id"],
                "confidence": a.get("confidence", "要検証"),
                "evidence": a.get("evidence", ""),
                "source": a.get("source", ""),
            })
        canon = e.get("canonical")
        if canon:
            alias_rows.append({
                "name": canon,
                "entity_id": e["id"],
                "confidence": "表記一致",
                "evidence": "代表表記（台帳）",
                "source": "ledger-canonical",
            })
        names.extend(alias_rows)
        if kind in CONCEPT_KINDS:
            concepts.append(rec)
        elif kind in ENTITY_KINDS:
            rec.setdefault("kind_group", "entity")
            entities.append(rec)
        else:
            # 想定外 kind は concepts へ（機械スキャンで 0 を要求）
            rec["kind_group"] = "concept"
            concepts.append(rec)

    out_dir = L2_RUNS / OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"generated_at": datetime.now().isoformat(timespec="seconds"), "source_run": BASE, "schema": "v4-layers"}
    (out_dir / "entities.json").write_text(json.dumps({"meta": meta, "entities": entities}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "names.json").write_text(json.dumps({"meta": meta, "names": names}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "roles.json").write_text(json.dumps({"meta": meta, "roles": roles}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "concepts.json").write_text(json.dumps({"meta": meta, "concepts": concepts}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "audit").mkdir(exist_ok=True)

    # 機械スキャン（移行保全検証）
    src_alias_rows = sum(len(a.get("aliases", [])) + (1 if a.get("canonical") else 0) for a in ents)
    scan = {
        "source_entities": len(ents),
        "entities_out": len(entities),
        "concepts_out": len(concepts),
        "names_out": len(names),
        "names_expected": src_alias_rows,
        "roles_out": len(roles),
        "entity_kind_vocab": sorted({e.get("kind") for e in entities}),
        "concept_kind_vocab": sorted({c.get("kind") for c in concepts}),
        "id_preserved": sorted({e["id"] for e in ents}) == sorted({e["id"] for e in entities} | {c["id"] for c in concepts}),
    }
    scan["ok"] = (scan["names_out"] == scan["names_expected"]) and scan["id_preserved"] and all(
        k in ENTITY_KINDS for k in scan["entity_kind_vocab"]) and all(k in CONCEPT_KINDS for k in scan["concept_kind_vocab"])
    (out_dir / "audit/changes.json").write_text(json.dumps(scan, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps({
        "run_id": OUT, "derived_from": BASE,
        "strategy": "v4 layers: entities/names/roles/concepts split (DESIGN-layers-v4.md)",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stats": scan}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("V4 SCAN:", json.dumps(scan, ensure_ascii=False))


if __name__ == "__main__":
    main()
