#!/usr/bin/env python3
"""v9: kind 語彙の正準化（決定論フォールディング）。

Usage: python scripts/build_l2_ledger_v9_kind.py <base_run_id> <out_run_id>
Input : work/allusionist_v2/L2/runs/<base>/entities.json
Output: runs/<out>/{entities.json, audit/changes.json, run.json}

正準 10 種: character/organization/location/creature/item/terminology/motif/
            phrase/relationship/event
- id は不変（README P1）。kind のみ run 差分として正準化する（README: kind 変更は差分）。
- 裁定済み kind_votes の根拠は保持、notes にフォールディング来歴を追記。
- kind 空は prefix から復元。prefix は歴史的標識として保持し notes に記録。
"""
import json
import sys
from datetime import datetime
from pathlib import Path

L2_RUNS = Path("C:/Users/d5dx/Downloads/Code/AllusionistWiki_work/work/allusionist_v2/L2/runs")

CANON = {"character", "organization", "location", "creature", "item",
         "terminology", "motif", "phrase", "relationship", "event"}

FOLD = {
    "character": "character", "organization": "organization",
    "location": "location", "creature": "creature", "item": "item",
    "terminology": "terminology", "motif": "motif", "phrase": "phrase",
    "relationship": "relationship", "event": "event",
    # 固有名詞性の強い語彙
    "deity": "character",
    # 具体的な物品・软件
    "app": "item", "software": "item", "clothing": "item", "part": "item",
    # 場所系
    "place": "location", "building": "location", "structure": "location",
    "celestial_body": "location",
    # 集団・組織系
    "group": "organization", "institution": "organization",
    # 発生・出来事系
    "action": "event", "event_context": "event", "game": "event",
    "phenomenon": "event",
    # 幻視・意匠
    "phantom": "motif",
    # 語彙の広義（用語）へ寄せるもの
    "magic": "terminology", "spell": "terminology", "spell_effect": "terminology",
    "skill": "terminology", "technique": "terminology", "ritual": "terminology",
    "ability": "terminology", "character_ability": "terminology",
    "race": "terminology", "character_class": "terminology", "role": "terminology",
    "system": "terminology", "brand": "terminology", "rule": "terminology",
    "concept": "terminology", "technology": "terminology",
    "plan": "terminology", "strategy": "terminology", "effect": "terminology",
    "emotion": "terminology", "institution": "terminology",
}

PREFIX_KIND = {
    "char": "character", "term": "terminology", "org": "organization",
    "item": "item", "motif": "motif", "phrase": "phrase",
    "rel": "relationship", "relation": "relationship",
    "loc": "location", "event": "event", "creature": "creature",
}

import re

# 語彙規則（prefix より優先）: canonical 表記から kind を判定する。
_COMB = re.compile(r"^(.+?)と(.+)$")
_PERSON_TAIL = re.compile(r"(女性|男性|少女|少年|男|女|人|者|王|姫|王女|博士|先生|師|戦士|騎士|魔法使い|達|たち|ども|ズ|上官|上司|部下|青年|老人|老婆|赤子|乳児|王太子|王子|皇子)$")
_PLACE_MARK = re.compile(r"(頂$|内部|店内|館内|屋内|室内|中$|内$|塔$|街$|都市$|世界$|階層$|宮$|殿$|館$|部屋$|森$|山$|川$|海$|空$|遺跡$|領$|港$|村$|島$|谷$|平原$|通路$|坑道$)")
_BODY_OBJ = re.compile(r"(舌|目|眼球|腕|手|足|脚|心$|臓器|鎧|剣|杖|靴|服|冠|指|尾|翼|牙|面$|顔$|頭部$|肉塊|爪|皮$|骨$|角$)$")
_ANIMAL_TAIL = re.compile(r"(犬|猫|狼|鳥|鷹|鷲|蛇|蟲|虫|魚|獣|竜|龍|兎|虎|蜥蜴|鼠|蛙|熊|猿|鹿|馬|蠑螈|水棲生物)$")
_RULE_WORDS = {"校則", "掟", "規則", "義務", "ルール", "禁止", "法"}


def main():
    base_run, out_run = sys.argv[1], sys.argv[2]
    rd = L2_RUNS / base_run
    data = json.loads((rd / "entities.json").read_text(encoding="utf-8"))
    ents = data["entities"]

    # 実在キャラ名集合（語彙規則用: kind=character および歴史的 prefix char を含む）
    names_char = set()
    for e in ents:
        is_char = e.get("kind") == "character" or e["id"].startswith("E_char_")
        if is_char:
            nm = (e.get("canonical") or "").strip()
            if nm:
                names_char.add(nm)
            for a in e.get("aliases", []) or []:
                if a.get("alias"):
                    names_char.add(a["alias"].strip())

    def head_strs(nm):
        out = [nm]
        m = re.match(r"^([^()（）\[\]]+)", nm)
        if m and m.group(1).strip():
            out.append(m.group(1).strip())
        # 括弧内の注記語も対象（例:「アキラの影分身(自動鎧)」→ 自動鎧）
        for mm in re.finditer(r"[()（）\[\]]{1}([^()（）\[\]]+)[()（）\[\]]{1}", nm):
            s = mm.group(1).strip()
            if s:
                out.append(s)
        return [s for s in out if s]

    def lex_kind(nm, pfx):
        """prefix より優先の語彙規則で kind を判定する。"""
        heads = head_strs(nm)
        cm = _COMB.match(nm)
        if cm and cm.group(1) in names_char and cm.group(2) in names_char:
            return "relationship", "複合名（XとY、両名実在）"
        for h in heads:
            if h in names_char:
                # 頭語がキャラ名そのもの:「◯◯の□□」は所有格 → 末尾の対象種別で判定
                mm = re.match(r"^(.+?)の(.+)$", h)
                if mm and mm.group(1) in names_char:
                    tail = mm.group(2)
                    if _BODY_OBJ.search(tail):
                        return "item", "所有格（キャラ名の身体部位・物品）"
                    return "terminology", "所有格（キャラ名の用語・行為）"
                return "character", "実在キャラ名（head 一致）"
        if _COMB.match(nm) and any(nc in nm for nc in names_char):
            return "relationship", "複合名（片側+キャラ名）"
        if nm in _RULE_WORDS:
            return "terminology", "規範語"
        for s in heads:
            if _PERSON_TAIL.search(s):
                return "character", "人物語尾"
            if _ANIMAL_TAIL.search(s):
                return "creature", "動物語尾"
            if _PLACE_MARK.search(s):
                return "location", "場所語彙"
            if _BODY_OBJ.search(s):
                return "item", "身体部位・物品"
        # 頭語に実在キャラ名を含む（部分一致）で語尾規則が利かない → 本体台帳不在の側面名義。
        # kind は terminology とし、審査キューへ送る（台帳本体の要欠落補完）。
        for nc in sorted(names_char, key=len, reverse=True):
            if len(nc) >= 3 and nc in nm:
                review.append({"name": nm, "hit": nc})
                return "terminology", "キャラ名部分一致（本体不在・審査キュー）"
        return PREFIX_KIND.get(pfx, "terminology"), "prefix 復元"

    changes = []
    review = []
    folds = 0
    empties = 0
    for e in ents:
        k = e.get("kind", "")
        old = k
        new = None
        if k in CANON:
            continue
        pfx = e["id"].split("_", 2)[1] if e["id"].count("_") >= 2 else ""
        if k == "" or k == "unknown" or k is None:
            new, basis = lex_kind((e.get("canonical") or "").strip(), pfx)
            empties += 1
        else:
            new = FOLD.get(k)
            basis = "v9 フォールディング"
        nm2 = (e.get("canonical") or "").strip()
        nms = head_strs(nm2)
        if new in ("terminology", "organization") and nm2:
            if any(_PERSON_TAIL.search(s) for s in nms):
                new, basis = "character", basis + "＋人物語尾 override"
            elif any(_ANIMAL_TAIL.search(s) for s in nms):
                new, basis = "creature", basis + "＋動物語尾 override"
            elif any(_PLACE_MARK.search(s) for s in nms):
                new, basis = "location", basis + "＋場所語彙 override"
            elif any(_BODY_OBJ.search(s) for s in nms):
                new, basis = "item", basis + "＋身体部位・物品 override"
        if new is None:
            new = "terminology"
            basis = "v9 収容（未登録語彙→terminology）"
        if new == old:
            continue
        folds += 1
        notes = e.get("notes", "")
        e["kind"] = new
        e["notes"] = (notes + "；" if notes else "") + f"v9 kind 正準化: {old!r}→{new!r}（{basis}。id の prefix は歴史的標識として不変）"
        changes.append({"id": e["id"], "canonical": e.get("canonical"),
                        "old_kind": old, "new_kind": new, "basis": basis})

    out_dir = L2_RUNS / out_run
    (out_dir / "audit").mkdir(parents=True, exist_ok=True)
    data["entities"] = ents
    (out_dir / "entities.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    with (out_dir / "audit/changes.json").open("w", encoding="utf-8") as f:
        json.dump({"base_run": base_run, "kind_changes": folds,
                   "empty_restored": empties, "review_queue": review,
                   "changes": changes},
                  f, ensure_ascii=False, indent=1)
    run = {"run_id": out_run, "created": datetime.now().isoformat(),
           "derived_from": base_run,
           "note": f"v9 kind 正準化: {folds} 件の kind を 10 種語彙へフォールディング（空 kind {empties} 件は prefix 復元）。id は不変。"}
    (out_dir / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    print("kind_changes=%d empty_restored=%d out=%s" % (folds, empties, out_dir))
    print("=== V9 KIND NORMALIZE DONE ===")


if __name__ == "__main__":
    main()
