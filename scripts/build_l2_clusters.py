"""S1+S2 段: L1 facts 名義棚卸し → 公開 ID シード → 相関グラフ（clusters_draft）・裁定キュー生成。

L1⇒L2 実行計画 S1/S2（work/allusionist_v2/L2/README.md 2026-10-24 確定版）準拠。
Usage: python scripts/build_l2_clusters.py <run_id>
Producing in work/allusionist_v2/L2/runs/<run_id>/:
  inputs-manifest.json / clusters_draft.json / adjudication-queue.jsonl / rejected-candidates.jsonl
"""
import json
import sys
import collections
import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (L2_RUNS, L1_INPUT_RUNS, norm_key, parse_paren,
                      strip_suffix, load_facts, load_seed_pages, non_entity_reason)

DERIVED_TAILS = {"選": "election", "市": "city", "都市": "city",
                 "の右腕": "bodypart", "の幻影": "phantom", "党": "party", "派": "faction"}
PREFIX_NICKS = {"ちび": "nick", "でか": "nick", "小さな": "nick"}
PRONOUN_NORMS = {norm_key(p) for p in ("俺", "私", "僕")}


def main():
    if len(sys.argv) < 2:
        print("usage: build_l2_clusters.py <run_id>")
        sys.exit(2)
    run_id = sys.argv[1]
    out = L2_RUNS / run_id
    out.mkdir(parents=True, exist_ok=True)

    # ---- S0 入力凍結 -------------------------------------------------------
    surfaces = collections.defaultdict(lambda: {"count": 0, "kind_votes": collections.Counter(),
                                                "quotes": [], "fact_ids": []})
    n_facts = 0
    for d in load_facts():
        s = (d.get("subject") or "").strip()
        if not s:
            continue
        n_facts += 1
        rec = surfaces[s]
        rec["count"] += 1
        rec["kind_votes"][d.get("entity_type", "?")] += 1
        if len(rec["quotes"]) < 2:
            rec["quotes"].append({"ep": d.get("episode"), "para": d.get("paragraph"),
                                  "type": d.get("fact_type"),
                                  "q": (d.get("quote") or "")[:90]})
        if len(rec["fact_ids"]) < 10:
            rec["fact_ids"].append({"run": d.get("run"), "ch": d.get("episode"),
                                    "fact_id": d.get("fact_id")})

    seeds = load_seed_pages()
    manifest = {"run_id": run_id,
                "created": datetime.datetime.now().isoformat(timespec="seconds"),
                "derived_from": L1_INPUT_RUNS,
                "facts_total": n_facts, "surfaces_unique": len(surfaces),
                "seed_pages": len(seeds)}
    (out / "inputs-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("[gate] facts=%d surfaces=%d seeds=%d" % (n_facts, len(surfaces), len(seeds)))

    # ---- P7 非エンティティ機械フィルタ -------------------------------------
    rejected, kept = [], {}
    for s, rec in surfaces.items():
        r = non_entity_reason(s)
        if r:
            rejected.append({"subject": s, "reason": r, "count": rec["count"]})
        else:
            kept[s] = rec
    (out / "rejected-candidates.jsonl").write_text(
        "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in rejected), encoding="utf-8")

    # ---- 表記ゆれノード（norm_key = 自動統合単位） --------------------------
    nodes = {}
    def node(nk):
        if nk not in nodes:
            nodes[nk] = {"norm": nk, "surfaces": [], "seed_ids": [],
                         "kind_votes": collections.Counter(), "count": 0,
                         "quotes": [], "fact_ids": [], "paren_edges": []}
        return nodes[nk]

    for s, rec in kept.items():
        main, paren = parse_paren(s)
        nk = norm_key(main)
        nd = node(nk)
        nd["surfaces"].append({"surface": s, "count": rec["count"]})
        nd["kind_votes"].update(rec["kind_votes"])
        nd["count"] += rec["count"]
        nd["quotes"] += rec["quotes"][:1]
        nd["fact_ids"] = (nd["fact_ids"] + rec["fact_ids"])[:10]
        if paren:
            pk = norm_key(paren)
            if pk in PRONOUN_NORMS:
                nd["paren_edges"].append({"to": pk, "auto": False, "type": "代名詞注記"})
            elif pk != nk:
                nd["paren_edges"].append({"to": pk, "auto": True, "type": "括弧注記"})

    for sid, sd in seeds.items():
        nd = node(sd["norm"])
        nd["seed_ids"].append({"id": sid, "kind": sd["kind"], "display": sd["display"]})
        nd["kind_votes"][sd["kind"]] += 3  # P5 prior 票

    # ---- 相関エッジ検出（P2・4 種） -----------------------------------------
    edges = []
    seen_edges = set()
    def add_edge(a, b, typ, auto):
        key = (a, b, typ)
        if a == b or key in seen_edges:
            return
        seen_edges.add(key)
        edges.append({"a": a, "b": b, "type": typ, "auto": auto})

    # 括弧注記（表記ゆれ級は auto、代名詞注記は裁定）
    for nk, nd in nodes.items():
        for pe in nd["paren_edges"]:
            if pe["to"] in nodes:
                add_edge(nk, pe["to"], pe["type"], pe["auto"])

    # 後方/前方の接尾・接頭構造
    for a in list(nodes):
        # 敬称除去一致
        t = strip_suffix(a)
        if t != a and t in nodes:
            add_edge(t, a, "敬称", False)
        # 前方一致: a = sub + tail（派生語・省略）
        for k in range(2, len(a)):
            sub, tail = a[:k], a[k:]
            if sub in nodes:
                if tail in DERIVED_TAILS:
                    add_edge(sub, a, "関連語", False)
                elif len(tail) <= 4:
                    add_edge(sub, a, "省略・あだ名", False)
        # 後方一致: a = head + sub（あだ名接頭）
        for k in range(1, len(a) - 1):
            head, sub = a[:k], a[k:]
            if sub in nodes and head in PREFIX_NICKS:
                add_edge(sub, a, "あだ名", False)

    # ---- 自動統合（表記ゆれ・括弧注記）の連結成分 ---------------------------
    parent = {nk: nk for nk in nodes}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for e in edges:
        if e["auto"] and e["a"] in parent and e["b"] in parent:
            union(e["a"], e["b"])
    groups = collections.defaultdict(list)
    for nk in nodes:
        groups[find(nk)].append(nk)

    # ---- 裁定キュー: 非自動エッジ + 多 kind 断片 + kind 同数 ---------------
    gq = {}
    def qadd(gk, members, etype):
        gq.setdefault(gk, {"members": set(), "edge_types": set()})
        gq[gk]["members"].update(members)
        gq[gk]["edge_types"].add(etype)
    for e in edges:
        if e["auto"]:
            continue
        a, b = find(e["a"]), find(e["b"])
        ga, gb = groups.get(a, []), groups.get(b, [])
        ca = sum(nodes[nk]["count"] for nk in ga)
        cb = sum(nodes[nk]["count"] for nk in gb)
        seed_involved = any(nodes[nk]["seed_ids"] for nk in ga + gb)
        # 証拠フィルタ: 縁の双方に使用票 3 以上 or 公開 ID 関与がなければ既定分離（裁定不要）
        if not seed_involved and (min(ca, cb) < 3):
            continue
        qadd("rel:" + "_".join(sorted([a, b]))[:60],
             set(ga) | set(gb), e["type"])
    for nk, nd in nodes.items():
        if len({s["kind"] for s in nd["seed_ids"]}) > 1:
            qadd("multi-kind:" + nk, groups.get(find(nk), [nk]), "seed-multi-kind")
        kv = [c for _, c in nd["kind_votes"].most_common()]
        if len(kv) >= 2 and kv[0] == kv[1]:
            qadd("kind-tie:" + nk, groups.get(find(nk), [nk]), "kind-tie")

    with open(out / "adjudication-queue.jsonl", "w", encoding="utf-8") as f:
        nq = 0
        for gk, gv in sorted(gq.items()):
            mem = []
            for nk in sorted(gv["members"]):
                nd = nodes.get(nk)
                if not nd:
                    continue
                mem.append({"norm": nk, "surfaces": nd["surfaces"],
                            "seed_ids": nd["seed_ids"],
                            "kind_votes": dict(nd["kind_votes"]),
                            "count": nd["count"], "quotes": nd["quotes"][:2]})
            f.write(json.dumps({"id": gk, "edge_types": sorted(gv["edge_types"]),
                                "members": mem}, ensure_ascii=False) + "\n")
            nq += 1

    # ---- clusters_draft: 自動統合後のグループ台帳（裁定前） -----------------
    draft = []
    for root, members in groups.items():
        g = {"group": root, "members": [], "kind_votes": collections.Counter(), "count": 0}
        for nk in members:
            nd = nodes[nk]
            g["members"].append({"norm": nk, "surfaces": nd["surfaces"], "seed_ids": nd["seed_ids"]})
            g["kind_votes"].update(nd["kind_votes"])
            g["count"] += nd["count"]
        kv = g["kind_votes"].most_common()
        resolved = None
        if kv:
            if len(kv) == 1:
                resolved = kv[0][0]
            elif kv[0][1] >= 3 * kv[1][1] and kv[0][1] >= 5:
                resolved = kv[0][0]
        draft.append({"group": root, "members": g["members"], "count": g["count"],
                      "kind_votes": dict(g["kind_votes"]),
                      "kind_mechanical": resolved,
                      "needs_adjudication": resolved is None})
    (out / "clusters_draft.json").write_text(json.dumps(
        {"schema": "l2-clusters-draft/1", "run": run_id, "groups": draft},
        ensure_ascii=False, indent=1), encoding="utf-8")

    n_multi = sum(1 for d in draft
                  if len({s["id"] for m in d["members"] for s in m["seed_ids"]}) > 1)
    print("[done] groups=%d adjudication_queue=%d rejected=%d multi-kind-groups=%d"
          % (len(draft), nq, len(rejected), n_multi))
    print("=== BUILD L2 CLUSTERS DONE ===")


if __name__ == "__main__":
    main()
