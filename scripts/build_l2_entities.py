"""S4 段: 裁定確定 clusters → 台帳射影（entities.json）+ 話単位来歴（aliases/）+ rejected 台帳。

Usage: python scripts/build_l2_entities.py <run_id>
Reads  runs/<id>/clusters_draft.json, adjudications*.jsonl, rejected-candidates.jsonl
Writes runs/<id>/entities.json, runs/<id>/aliases/chNNNN.json, runs/<id>/relations.jsonl
"""
import json
import sys
import collections
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (L2_RUNS, KIND_PREFIX, load_facts, norm_key, parse_paren,
                      ep_sort_key)

CONF_RANK = {"明言": 3, "蓋然性高": 2, "要検証": 1}


def main():
    if len(sys.argv) < 2:
        print("usage: build_l2_entities.py <run_id>")
        sys.exit(2)
    run_id = sys.argv[1]
    out = L2_RUNS / run_id

    draft = json.loads((out / "clusters_draft.json").read_text(encoding="utf-8"))

    # ---- 裁定読み込み -------------------------------------------------------
    adj = {}  # (group_root, norm) -> decisions list
    group_decisions = collections.defaultdict(list)
    for p in out.glob("adjudications*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            group_decisions[r["id"]].extend(r.get("decisions", []))

    # グループ構造（members: norm -> info）を group root 単位で再構成
    groups = {}
    for d in draft["groups"]:
        mem = {}
        for m in d["members"]:
            mem[m["norm"]] = m
        groups[d["group"]] = {"members": mem, "kind_mechanical": d.get("kind_mechanical")}

    # norm -> group root 対応（裁定 id は root を含む形で作られている）
    norm2root = {}
    for root, g in groups.items():
        for nk in g["members"]:
            norm2root[nk] = root

    # ---- 台帳ノード（union-find: 表記ゆれ auto + alias 裁定） ---------------
    parent = {nk: nk for nk in norm2root}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    # auto（表記ゆれ）マージは draft のグループ単位で実施
    for root, g in groups.items():
        first = next(iter(g["members"]))
        for nk in g["members"]:
            union(first, nk)

    merge_conf = collections.defaultdict(lambda: "明言")  # 根拠の最大確度
    notes = collections.defaultdict(list)
    adjudicated = set()
    relations = []

    def norm_of_canonical(c, root):
        if c in norm2root:
            return c
        if c:
            # 公開 ID 指定 → seed の norm
            for nk, m in groups.get(root, {}).get("members", {}).items():
                for s in m["seed_ids"]:
                    if s["id"] == c:
                        return nk
        return None

    for gid, decs in group_decisions.items():
        for dec in decs:
            nk = dec.get("norm")
            if nk not in norm2root:
                continue
            adjudicated.add(nk)
            v = dec.get("verdict")
            conf = dec.get("confidence") or "要検証"
            reason = dec.get("reason") or ""
            tgt = norm_of_canonical(dec.get("canonical"), gid)
            notes[nk].append("%s:%s" % (v, reason[:60])[:80])
            if v == "alias" and tgt:
                union(nk, tgt)
                r = merge_conf[find(nk)]
                if CONF_RANK.get(conf, 1) > CONF_RANK.get(r, 1):
                    pass
                # 統合確度は最小側（弱い根拠に支配される）
                if CONF_RANK.get(conf, 1) < CONF_RANK.get(merge_conf[find(nk)], 3):
                    merge_conf[find(nk)] = conf
            elif v == "related":
                relations.append({"from": nk, "to": tgt, "edge": "related",
                                  "confidence": conf, "reason": reason[:80]})

    clusters = collections.defaultdict(list)
    for nk in norm2root:
        clusters[find(nk)].append(nk)

    # ---- facts から surface→min anchor / refs（1 パス） ---------------------
    # surface(raw) -> norm（括弧除去後）対応は clusters_draft にある
    surf2norm = {}
    seed_of_norm = {}
    for root, g in groups.items():
        for nk, m in g["members"].items():
            for s in m["surfaces"]:
                surf2norm[s["surface"]] = nk
            seed_of_norm[nk] = m["seed_ids"]

    anchors = collections.defaultdict(lambda: {"ep": None, "para": None})
    refs = collections.defaultdict(list)
    ep_maps = collections.defaultdict(dict)  # episode -> surface -> (will resolve to id later)
    for d in load_facts():
        s = (d.get("subject") or "").strip()
        nk = surf2norm.get(s)
        if not nk:
            main, paren = parse_paren(s)
            nk = surf2norm.get(main)
        if not nk:
            continue
        ep, para = d.get("episode", ""), d.get("paragraph", "")
        a = anchors[nk]
        if a["ep"] is None or (ep_sort_key(ep) < ep_sort_key(a["ep"])):
            a["ep"], a["para"] = ep, para
        if len(refs[nk]) < 3:
            refs[nk].append("%s:facts/%s#%s" % (d.get("run"), ep, d.get("fact_id")))
        ep_maps[ep][s] = nk

    # ---- entity 生成 --------------------------------------------------------
    entities = []
    norm2entity = {}
    for root, members in clusters.items():
        # canonical 選択: 公開 ID 優先 → 最多 surface
        seeds = []
        for nk in members:
            seeds += seed_of_norm.get(nk, [])
        votes = collections.Counter()
        for nk in members:
            for sd in seed_of_norm.get(nk, []):
                votes[sd["kind"]] += 3
            # facts 票（kind_votes は per-norm のため再集計は重い → 裁定 kind を優先）
        kind = groups[0]["kind_mechanical"]  # placeholder
        # group 単位 kind_mechanical を集める
        kind_votes_all = collections.Counter()
        kmech = None
        for nk in members:
            g = groups[norm2root[nk]]
            kind_votes_all.update(g["kind_mechanical"] and {} or {})
            # kind_votes は draft 側に集計済み → ここでは使わない: 裁定 kind を優先
        kinds_dec = [dec.get("kind") for gid, ds in group_decisions.items()
                     for dec in ds if dec.get("norm") in members and dec.get("kind")]
        kind_counts = collections.Counter(kinds_dec)
        kind = kind_counts.most_common(1)[0][0] if kind_counts else (
            seeds[0]["kind"] if seeds else "term")
        if seeds:
            eid = seeds[0]["id"]
            canonical = seeds[0]["display"]
        else:
            best = None
            for nk in members:
                g = groups[norm2root[nk]]
                for s in g["members"][0]["surfaces"] if False else []:
                    pass
            # 最多 surface を代表に
            cand = []
            for nk in members:
                for s in groups[norm2root[nk]]["members"]:
                    pass
            surf_counts = collections.Counter()
            for nk in members:
                for m in groups[norm2root[nk]]["members"]:
                    pass
            for nk in members:
                mem = groups[norm2root[nk]]["members"]
                for mm in mem:
                    for s in mm["surfaces"]:
                        surf_counts[s["surface"]] += s["count"]
            if not surf_counts:
                continue
            canonical = surf_counts.most_common(1)[0][0]
            slug = re.sub(r"[ /\\：:・「」『』（）()]", "_", canonical)[:40]
            kp = KIND_PREFIX.get(kind, "E_term")
            eid = "%s_%s" % (kp, slug)
        aliases = sorted({s["surface"] for nk in members
                          for m in [groups[norm2root[nk]]["members"]]
                          for s in [mm for mm in m]
                          for s in s["surfaces"]}, key=len, reverse=True)
        # aliases 収集（正確に）
        aliases = set()
        for nk in members:
            for mm in groups[norm2root[nk]]["members"]:
                for s in mm["surfaces"]:
                    aliases.add(s["surface"])
        anchor = anchors.get(root) or anchors.get(members[0], {"ep": None, "para": None})
        kconf = "蓋然性高" if kinds_dec else "要検証"
        notes_all = sorted({n for nk in members for n in notes.get(nk, [])})[:6]
        ent = {"id": eid, "canonical": canonical,
               "aliases": sorted(aliases),
               "kind": kind,
               "first_seen": {"ch": anchor.get("ep"), "para": anchor.get("para")},
               "l1_refs": refs.get(members[0], [])[:3],
               "merge_evidence": merge_conf.get(root, "蓋然性高"),
               "kind_confidence": kconf,
               "notes": notes_all}
        entities.append(ent)
        for nk in members:
            norm2entity[nk] = eid

    entities.sort(key=lambda e: -len(e["aliases"]))
    (out / "entities.json").write_text(json.dumps(
        {"schema": "l2-entities/1", "run": run_id, "count": len(entities),
         "entities": entities}, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "relations.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in relations), encoding="utf-8")

    # ---- 話単位来歴 aliases/chNNNN.json ------------------------------------
    adir = out / "aliases"
    adir.mkdir(exist_ok=True)
    for ep, smap in ep_maps.items():
        m = {}
        for s, nk in smap.items():
            eid = norm2entity.get(nk)
            if eid:
                m[s] = eid
        (adir / ("%s.json" % ep)).write_text(
            json.dumps(m, ensure_ascii=False, indent=0), encoding="utf-8")

    n_ad = len(adjudicated)
    print("[done] entities=%d relations=%d adjudicated_norms=%d episodes=%d"
          % (len(entities), len(relations), n_ad, len(ep_maps)))
    print("=== BUILD L2 ENTITIES DONE ===")


if __name__ == "__main__":
    main()
