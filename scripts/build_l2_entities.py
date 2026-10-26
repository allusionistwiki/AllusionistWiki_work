"""S4 段: 裁定済み相関グループ → L2 正規化エンティティ台帳を生成。

Usage: python scripts/build_l2_entities.py <run_id>
Input : runs/<id>/clusters_draft.json（表記ゆれ自動群）, adjudication-queue.jsonl,
        adjudications*.jsonl（裁定）+ L1 facts（来歴・kind 集計）
Output: runs/<id>/entities.json, aliases/chNNNN.json（話単位来歴）, relations.jsonl
検証: kind 全付与 / first_seen ¶N 到達 / ID 衝突 0 / 未裁定 0 をサマリ出力。
"""
import json
import re
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import (L2_RUNS, L1_INPUT_RUNS, norm_key, load_seed_pages,
                      load_facts, KIND_PREFIX, ep_sort_key)

RUN = sys.argv[1]
OUT = L2_RUNS / RUN


def jl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def para_num(p):
    m = re.search(r"(\d+)", str(p or ""))
    return int(m.group(1)) if m else 0


class DSU:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def main():
    # ---- facts 集計: norm → surfaces/kind票/アンカー/l1_refs ---------------
    surf = collections.defaultdict(lambda: {
        "surfaces": collections.Counter(), "kind": collections.Counter(),
        "anchors": None, "refs": []})
    ep_surface = collections.defaultdict(set)
    for d in load_facts(L1_INPUT_RUNS):
        subj = d.get("subject")
        s = ((subj.get("surface") if isinstance(subj, dict) else subj) or "").strip()
        if not s:
            continue
        nk = norm_key(s)
        v = surf[nk]
        v["surfaces"][s] += 1
        et = d.get("entity_type")
        if et:
            v["kind"][et] += 1
        ep = d.get("episode")
        pn = para_num(d.get("paragraph"))
        k = (ep_sort_key(ep), pn)
        if ep and (v["anchors"] is None or k < v["anchors"][0]):
            v["anchors"] = (k, ep, pn)
        if len(v["refs"]) < 3:
            v["refs"].append({"run": d.get("run"), "ep": ep,
                              "fact_id": d.get("fact_id")})
        ep_surface[ep].add(s)
    ep_surface.pop(None, None)

    # ---- DSU: 自動群 → 裁定 alias ------------------------------------------
    dsu = DSU()
    draft = json.loads((OUT / "clusters_draft.json").read_text(encoding="utf-8"))
    auto_edges = set()
    for g in draft["groups"]:
        ms = [m["norm"] for m in g["members"]]
        # 自動統合は表記ゆれ（同一 norm_key）のみ。関連語・派生語は裁定に委ねる。
        by_key = {}
        for m in ms:
            by_key.setdefault(norm_key(m), []).append(m)
        for k, group in by_key.items():
            for m in group[1:]:
                auto_edges.add(tuple(sorted((group[0], m))))

    queue = {r["id"]: r for r in jl(OUT / "adjudication-queue.jsonl")}
    decisions_raw = []
    for p in sorted(OUT.glob("adjudications*.jsonl")):
        if "_v2" in p.name:
            continue
        decisions_raw += jl(p)
    d_by_id = {}
    for d in decisions_raw:
        d_by_id[d["id"]] = d          # 複数ラウンドでは最終ラウンドを採用
    decisions_all = list(d_by_id.values())
    adjudicated_kind = {}
    rel_rows = []
    rel_seen = set()
    alias_edges = set()      # 明示された裁定辺の集合（a,b）のペア — 推移閉包は作らない
    for d in decisions_all:
        row = queue.get(d["id"])
        bucket = collections.defaultdict(list)
        for m in d.get("decisions", []):
            nk = m.get("norm")
            if m.get("kind"):
                adjudicated_kind.setdefault(nk, collections.Counter())[m["kind"]] += 5
            if m.get("verdict") == "alias":
                canon = m.get("canonical")
                if canon:
                    alias_edges.add(tuple(sorted((nk, norm_key(canon)))))
                bucket[norm_key(canon) if canon else nk].append(nk)
        if row:
            vt = {m["norm"]: m.get("verdict") for m in d.get("decisions", [])
                  if m.get("norm")}
            ms = [m["norm"] for m in row.get("members", [])]
            etype = (row.get("edge_types") or ["relation"])[0]
            for i, mi in enumerate(ms):
                if vt.get(mi) == "related":
                    for j, mj in enumerate(ms):
                        if i != j:
                            rel_key = (etype, mi, mj)
                            if rel_key in rel_seen:
                                continue
                            rel_seen.add(rel_key)
                            rel_rows.append({"type": etype, "from": mi, "to": mj,
                                             "gid": d["id"], "run": RUN})
    missing = len(set(queue) - {d["id"] for d in decisions_all})

    # ---- v2 再裁定（全話 evidence）+ 機械共起 split を alias に適用 -------
    v2 = {}
    for p in sorted(OUT.glob("adjudications_v2*.jsonl")):
        for d in jl(p):
            v2[d["id"]] = {m.get("norm"): m for m in d.get("verdicts", [])
                           if m.get("norm")}
    mech_pairs = set()
    mech_path = OUT / "mech-splits.jsonl"
    if mech_path.exists():
        for d in jl(mech_path):
            mech_pairs.add(tuple(sorted((d["a"], d["b"]))))
    # ---- 裁定辺を「非推移」で適用。v2 完走後は v2 全面適用（v1 alias 辺は採らない）---
    accepted_edges = set()
    n_split = n_needs = 0
    v2_full = len(v2) >= len(queue)
    v2_keep = v2_split = 0
    if v2_full:
        canon1 = {}
        for d in decisions_all:
            for m in d.get("decisions", []):
                if m.get("verdict") == "alias" and m.get("canonical") and m.get("norm"):
                    canon1[m["norm"]] = norm_key(m["canonical"])
        for gid, vv in v2.items():
            for n, d2 in vv.items():
                dec = d2.get("decision")
                if dec == "keep":
                    canon = d2.get("canonical")
                    canon = norm_key(canon) if canon else canon1.get(n)
                    if canon and canon != n:
                        reason = d2.get("reason") or ""
                        cited = bool(re.search(r"ch\d", reason))
                        no_ev = ("証拠が0" in reason) or ("証拠なし" in reason) or ("データなし" in reason)
                        accepted_edges.add((n, canon,
                                            d2.get("confidence"), cited, no_ev))
                        v2_keep += 1
                elif dec == "split":
                    v2_split += 1
                elif dec == "needs":
                    n_needs += 1
        # ---- 連結成分サイズ上限 24: 超過分は支持度の低い邊から切る（ハブ連鎖の膨張防止）---
        score = {"明言": 3, "蓋然性高": 2, "要検証": 1}
        cand = sorted(((score.get(conf, 0), cited, no_ev, n, canon)
                       for (n, canon, conf, cited, no_ev) in accepted_edges
                       if cited and not no_ev),
                      key=lambda x: (-x[0], -x[1]))
        parent = {n: n for n in set([e[3] for e in cand] + [e[4] for e in cand])}
        size = {n: 1 for n in parent}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        MAXC = 10
        used_edges = set()
        n_hub_cut = 0
        for s, c, ne, a, b in cand:
            ra, rb = find(a), find(b)
            if ra == rb:
                used_edges.add((a, b))
                continue
            sa, sb = size[ra], size[rb]
            if sa + sb > MAXC:
                n_hub_cut += 1
                continue
            parent[rb] = ra
            size[ra] = sa + sb
            used_edges.add((a, b))
        n_no_cite = len(accepted_edges) - len(cand)
        accepted_edges = used_edges
        print("v2_full: keep=%d split=%d needs=%d no_cite=%d hub_cut=%d accepted=%d mech_pairs=%d"
              % (v2_keep, v2_split, n_needs, n_no_cite, n_hub_cut,
                 len(accepted_edges), len(mech_pairs)))
        for a, b in accepted_edges:
            if tuple(sorted((a, b))) not in mech_pairs:
                dsu.union(a, b)
    else:
        for (a, b) in alias_edges:
            blocked = False
            for gid, vv in v2.items():
                for n in (a, b):
                    dec = (vv.get(n) or {}).get("decision")
                    if dec == "split":
                        blocked = True
                        n_split += 1
                    elif dec == "needs":
                        blocked = True
                        n_needs += 1
            if tuple(sorted((a, b))) in mech_pairs:
                blocked = True
                n_split += 1
            if not blocked:
                accepted_edges.add((a, b))
    # 表記ゆれ自動辺（mech 共起で遮断された辺を推移で橋渡ししない）
    dsu2 = DSU()
    n_mech_cut = 0
    all_edges = list(auto_edges) + list(accepted_edges)
    blocked_pairs = set(mech_pairs)
    for gid, vv in v2.items():
        for n, d2 in vv.items():
            if d2.get("decision") == "split":
                blocked_pairs.add(tuple(sorted((n, d2.get("canonical") or ""))))
    # auto 辺も v2 判定に従う: split/needs は即断、keep は引用付きのみ（v1 alias 辺は v2 で置換済み）
    n_auto_cut = 0
    for (a, b) in list(auto_edges):
        vna = vnb = None
        for gid, vv in v2.items():
            vna = vv.get(a, vna)
            vnb = vv.get(b, vnb)
        if vna is not None and vna.get("decision") == "split":
            blocked_pairs.add((a, b))
            n_auto_cut += 1
        elif vnb is not None and vnb.get("decision") == "split":
            blocked_pairs.add((a, b))
            n_auto_cut += 1
        elif (vna is not None and vna.get("decision") == "needs") or \
             (vnb is not None and vnb.get("decision") == "needs"):
            blocked_pairs.add((a, b))
            n_auto_cut += 1
        elif (vna is not None and vna.get("decision") == "keep") or \
             (vnb is not None and vnb.get("decision") == "keep"):
            reason = (vna.get("reason") if vna and vna.get("decision") == "keep"
                      else (vnb.get("reason") if vnb and vnb.get("decision") == "keep" else "")) or ""
            if not re.search(r"ch\d", reason) or "証拠が0" in reason or "データなし" in reason:
                blocked_pairs.add((a, b))
                n_auto_cut += 1
    for (a, b) in all_edges:
        if tuple(sorted((a, b))) in blocked_pairs:
            n_mech_cut += 1
        else:
            dsu2.union(a, b)
    # v2 の kind は裁定 kind として反映
    for gid, vv in v2.items():
        for n, d2 in vv.items():
            if d2.get("kind"):
                adjudicated_kind.setdefault(n, collections.Counter())[d2["kind"]] += 5
    print("edges: v1=%d accepted=%d split=%d needs=%d mech_pairs=%d mech_cut=%d v2_rows=%d"
          % (len(alias_edges), len(accepted_edges), n_split, n_needs,
             len(mech_pairs), n_mech_cut, len(v2)))
    dsu = dsu2

    # ---- 合成 → entities ----------------------------------------------------
    seeds = {}
    for sd in load_seed_pages().values():
        seeds.setdefault(sd["norm"], []).append(sd)

    comp = collections.defaultdict(list)
    for nk in surf:
        comp[dsu.find(nk)].append(nk)

    id_used = set()
    entities = []
    for root, members in comp.items():
        kind_votes = collections.Counter()
        for nk in members:
            for k, c in surf[nk]["kind"].items():
                kind_votes[k] += c
            kind_votes.update(adjudicated_kind.get(nk, {}))
        seeds_all = []
        for nk in members:
            seeds_all += seeds.get(nk, [])
        for sd in seeds_all:
            kind_votes[sd["kind"]] += 3
        kind = kind_votes.most_common(1)[0][0] if kind_votes else "term"
        kind_conf = "裁定済" if any(nk in adjudicated_kind for nk in members) else "機械"

        all_s = collections.Counter()
        for nk in members:
            all_s.update(surf[nk]["surfaces"])
        anchors = [surf[nk]["anchors"] for nk in members if surf[nk]["anchors"]]
        anchors.sort(key=lambda a: a[0])
        refs = []
        for nk in members:
            refs += surf[nk]["refs"][:1]
        confs = []
        for d in decisions_all:
            for m in d.get("decisions", []):
                if m.get("norm") in members:
                    confs.append(m.get("confidence"))
        merge_ev = ("明言" if "明言" in confs else
                    "要検証" if "要検証" in confs else "蓋然性高")

        if seeds_all:
            primary = min(seeds_all, key=lambda s: s["id"])
            eid = primary["id"]
            canonical = primary["display"]
        else:
            if not all_s:
                continue
            canonical = max(all_s, key=lambda s: (all_s[s], len(s)))
            slug = re.sub(r"[ /\\：:・「」『』（）()\[\]<>|,，.。]", "_", canonical)[:40]
            eid = "%s_%s" % (KIND_PREFIX.get(kind, "E_term"), slug)
        while eid in id_used:
            eid += "x"
        id_used.add(eid)
        entities.append({
            "id": eid,
            "canonical": canonical,
            "aliases": sorted(all_s, key=lambda a: (-all_s[a], a)),
            "kind": kind,
            "kind_confidence": kind_conf,
            "merge_evidence": merge_ev,
            "first_seen": {"ch": anchors[0][1] if anchors else None,
                           "para": anchors[0][2] if anchors else None},
            "l1_refs": refs[:3],
            "seed_ids": sorted({s["id"] for s in seeds_all}),
            "fact_total": sum(all_s.values()),
        })
    norm2ent = {}
    for e in entities:
        for a in e["aliases"]:
            norm2ent.setdefault(norm_key(a), e["id"])

    entities.sort(key=lambda e: (-(len(e["aliases"])), -e["fact_total"], e["id"]))
    (OUT / "entities.json").write_text(json.dumps(
        {"schema": "l2-entities/1", "run": RUN, "count": len(entities),
         "entities": entities}, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---- 話単位 aliases/chNNNN.json ----------------------------------------
    adir = OUT / "aliases"
    adir.mkdir(exist_ok=True)
    total = 0
    eps = 0
    for ep, sset in sorted(ep_surface.items()):
        mp = {}
        for s in sorted(sset):
            eid = norm2ent.get(norm_key(s))
            if eid:
                mp[s] = eid
        if not mp:
            continue
        (adir / ("ch%s.json" % ep)).write_text(json.dumps(
            {"schema": "l2-alias/1", "run": RUN, "ep": ep, "map": mp},
            ensure_ascii=False, indent=1), encoding="utf-8")
        total += len(mp)
        eps += 1

    (OUT / "relations.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rel_rows),
        encoding="utf-8")

    # ---- 検証サマリ ----------------------------------------------------------
    kinds = collections.Counter(e["kind"] for e in entities)
    evs = collections.Counter(e["merge_evidence"] for e in entities)
    kc = collections.Counter(e["kind_confidence"] for e in entities)
    multi = sum(1 for e in entities if len(e["aliases"]) > 1)
    no_anchor = sum(1 for e in entities if not e["first_seen"]["ch"])
    print("entities=%d multi_alias=%d alias_rows=%d eps=%d relations=%d undecided=%d"
          % (len(entities), multi, total, eps, len(rel_rows), missing))
    print("by_kind=%s" % dict(kinds.most_common()))
    print("merge_evidence=%s kind_conf=%s" % (dict(evs), dict(kc)))
    print("no_anchor=%d id_collisions=%d"
          % (no_anchor, len(entities) - len(id_used)))
    print("=== L2 BUILD ENTITIES DONE ===")


if __name__ == "__main__":
    main()
