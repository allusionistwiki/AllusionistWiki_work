#!/usr/bin/env python3
"""v10 台帳: (1) 主人公 canonical 統合（シナモリアキラ 代表、品森晶/品森晶 アキラ/語り手を統合）
(2) 抽象名詞 character の kind 再分類（実読監査 0/23 不合格に対応）。id は不変。
用法: python scripts/build_l2_ledger_v10.py <base_run_id> <out_run_id>"""
import json
import sys
from datetime import datetime
from pathlib import Path

L2_RUNS = Path("C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/allusionist_v2/L2/runs")
BASE, OUT = sys.argv[1], sys.argv[2]

# (1) 主人公統合: 代表=シナモリアキラ（ch00018 本名明言/ch00459「品森晶＝イッツノの」同一性述語）
PRIMARY = "E_char_アキラ"
MERGE_INTO_PRIMARY = {"E_char_品森晶": "E_char_品森晶は Akira Shinamori の本名（ch00018 同一性述語）",
                      "E_char_品森晶_Akira_Shinamori": "本名ラテン表記（ch00018 同一性述語）",
                      "E_char_語り手": "作中メタ呼称（ch00018 前後「語っている俺」と同一）"}
# 側面名義の親設定（品森晶（X）→ シナモリアキラ）
ASPECT_PARENT_PREFIX = "品森晶（"

# (2) 抽象名詞 character → kind 再分類（2026-11-12 実読監査 23件: 拟人化主体行為なし）
KIND_RECLASS = {
    # 感情・概念 → terminology
    "感情": "terminology", "意識": "terminology", "精神": "terminology", "心": "terminology",
    "感情の揺らぎ": "terminology", "恐怖": "terminology", "怒り": "terminology", "喜び": "terminology",
    "絶望": "terminology", "愛": "terminology", "憎しみ": "terminology", "復讐": "terminology",
    "沈黙": "terminology", "記憶": "terminology", "存在": "terminology", "無": "terminology",
    "自己": "terminology", "権利": "terminology", "義務": "terminology", "使命": "terminology",
    "因果": "terminology", "運命": "terminology", "意味": "terminology", "価値": "terminology",
    "知識": "terminology", "叡智": "terminology", "教義": "terminology", "信仰": "terminology",
    "神秘": "terminology", "奇跡": "terminology", "秘密": "terminology", "謎": "terminology",
    "真実": "terminology", "嘘": "terminology", "正義": "terminology", "悪": "terminology",
    "時間": "terminology", "空間": "terminology", "全て": "terminology", "世界観": "terminology",
    "人生": "terminology", "日常": "terminology", "生活": "terminology",
    "神": "terminology", "神々": "terminology", "悪魔": "terminology",
    # 現象・出来事 → event
    "破壊": "event", "破滅": "event", "崩壊": "event", "終末": "event", "終焉": "event",
    "終結": "event", "消滅": "event", "滅び": "event", "死": "event", "生": "event",
    "発生": "event", "創世": "event", "開始": "event", "始まり": "event", "起源": "event",
    "再生": "event", "転生": "event", "浄化": "event", "融合": "event", "分離": "event",
    "衝突": "event", "戦争": "event", "争い": "event", "紛争": "event", "平和": "event",
    "混沌": "event", "秩序": "event",
}


def main():
    d = json.loads((L2_RUNS / BASE / "entities.json").read_text(encoding="utf-8"))
    ents = d["entities"]
    by_id = {e["id"]: e for e in ents}
    primary = by_id.get(PRIMARY)
    assert primary is not None, "primary missing"
    primary["canonical"] = "シナモリアキラ"
    primary["canonical_evidence"] = "ch00018 品森晶（シナモリアキラ）/ch000459 品森晶＝イッツノの 同一性述語。ネット上主名称として最多使用"
    primary_aliases = primary.setdefault("aliases", [])
    seen_alias = {rec.get("string") or rec.get("name") for rec in primary_aliases}

    changes = {"merged_canonical": 0, "aspect_parents": 0, "kind_reclass": 0}
    # (1a) 本体統合
    for eid, why in MERGE_INTO_PRIMARY.items():
        e = by_id.get(eid)
        if e is None:
            continue
        for rec in e.get("aliases", []):
            s = rec.get("string") or rec.get("name")
            if s and s not in seen_alias:
                norm = dict(rec)
                norm["name"] = s
                primary_aliases.append(norm)
                seen_alias.add(s)
        for s in [e.get("canonical")] + [x.get("string") or x.get("name") for x in e.get("aliases", [])]:
            if s and s not in seen_alias:
                primary_aliases.append({"name": s, "string": s, "confidence": "明言", "evidence": "ch00018 品森晶（シナモリアキラ）同一性述語"})
                seen_alias.add(s)
        e["merged_into"] = PRIMARY
        e["merged_confidence"] = "明言"
        e["merged_evidence"] = why
        changes["merged_canonical"] += 1
    # (1b) 品森晶（X）側面 → 親設定
    for e in ents:
        nm = e.get("canonical") or ""
        if nm.startswith(ASPECT_PARENT_PREFIX) and e.get("parent") != PRIMARY and "merged_into" not in e:
            e["parent"] = PRIMARY
            e["parent_confidence"] = "明言（品森晶＝シナモリアキラ 同一性述語）"
            changes["aspect_parents"] += 1

    # (1c) 実読監査済みの裸名義を明示 alias として本体に確定登録（v10 監査シート G1 40/40）
    REQUIRED = {
        "シナモリ・アキラ": "v10 実読監査: ch00257/ch00094/ch00046/ch00053 で呼称対象=主人公。中点付き表記ゆれ",
        "品森 晶": "v10 実読監査: 本名表記の空白変形（ch00018 同一性述語）",
        "語り手": "v10 実読監査: ch00351『語り手とは神なのか』は作中メタの主人公そのものへの問い",
    }
    for s, why in REQUIRED.items():
        if s not in seen_alias:
            primary_aliases.append({"name": s, "string": s, "confidence": "明言", "evidence": why})
            seen_alias.add(s)

    # (2) 抽象名詞 kind 再分類（head 一致のみ、側面名は親追随なので対象外）
    for e in ents:
        if e.get("kind") != "character" or "merged_into" in e:
            continue
        nm = e.get("canonical") or ""
        head = nm.split("(")[0].split("（")[0].strip()
        if head in KIND_RECLASS:
            e["kind"] = KIND_RECLASS[head]
            e["kind_confidence"] = "裁定済（2026-11-13 実読監査: 拟人化主体行為なし）"
            changes["kind_reclass"] += 1

    # 統合本体を alias 索引から除外するためのフラグは merged_into で代用（生成側で解決）
    d["generated_at"] = datetime.now().isoformat(timespec="seconds")
    meta = d.setdefault("meta", {})
    meta["run"] = OUT
    meta["strategy"] = "v10.0: protagonist canonical merge (シナモリアキラ, ch00018 evidence) + abstract-noun kind reclassification (0/23 実読不合格対応)"
    out_dir = L2_RUNS / OUT
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "entities.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    audit = {"changes": changes}
    (out_dir / "audit").mkdir(exist_ok=True)
    (out_dir / "audit/changes.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "run.json").write_text(json.dumps({
        "run_id": OUT, "derived_from": BASE,
        "strategy": "v10.0 protagonist canonical + abstract kind reclass",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "stats": changes}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("v10 done:", changes)


if __name__ == "__main__":
    main()
