"""S0 v3: L2 台帳の棚卸し入力を events 系エンティティ登録 + L1 ページへ拡張。

Usage: python scripts/build_l2_v3_inventory.py <l2_run_id>
Input : L1 runs events/*.jsonl（subject・entity_type・quote）
        vault wiki/entities/**（canonical_name・subtype・代表引用）
        現台帳 entities.json
Output: runs/<l2_run>/v3-inventory.jsonl  — 台帳外 surface の証拠パック（1 行 1 面）
        runs/<l2_run>/v3-review-queue.jsonl — 裁定投入用（親候補付き、compact）

親候補: 所有形 `XのY` の X が既知面 → parent 候補（最大 3、出現頻度順）。
既存台帳の所有形エンティティ（aspect 候補）も対象に含める。
"""
import json
import re
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS, L1_INPUT_RUNS, norm_key, load_facts

WIKI = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/wiki")
RUN = sys.argv[1]
OUT = L2_RUNS / RUN
MAX_Q = 2
QLEN = 80


def main():
    ents = json.loads((OUT / "entities.json").read_text(encoding="utf-8"))["entities"]
    known = {}
    for e in ents:
        known[norm_key(e["canonical"])] = e["canonical"]
        for a in e.get("aliases", []):
            known.setdefault(norm_key(a), e["canonical"])
    char_norms = {norm_key(e["canonical"]) for e in ents if e.get("kind") == "character"}
    for a in [norm_key(k) for k in known]:
        pass  # char set only from canonical

    usage = collections.Counter()
    etype = collections.defaultdict(collections.Counter)
    quotes = {}
    eps = collections.defaultdict(set)
    surfaces = collections.defaultdict(set)
    for rd in L1_INPUT_RUNS:
        ev_dir = L2_RUNS.parent.parent / "L1" / "runs" / rd / "events"
        if not ev_dir.exists():
            continue
        for p in ev_dir.glob("*.jsonl"):
            for l in p.read_text(encoding="utf-8").splitlines():
                if not l.strip():
                    continue
                d = json.loads(l)
                s = d.get("subject")
                s = ((s.get("surface") if isinstance(s, dict) else s) or "").strip()
                if not s:
                    continue
                nk = norm_key(s)
                usage[nk] += 1
                surfaces[nk].add(s)
                et = d.get("entity_type")
                if et:
                    etype[nk][et] += 1
                ep = d.get("episode")
                if ep:
                    eps[nk].add(ep)
                q = str(d.get("quote") or "")
                if len(quotes.get(nk, [])) < MAX_Q and q:
                    quotes.setdefault(nk, []).append(
                        {"ep": ep, "q": q[:QLEN]})

    # L1 ページ由来（台帳外 canonical_name）
    pages = collections.defaultdict(lambda: {"subtype": "", "q": []})
    for p in (WIKI / "entities").rglob("*.md"):
        t = p.read_text(encoding="utf-8")
        m = re.search(r"^canonical_name:\s*\"?([^\"\n]+)\"?", t, re.M)
        if not m:
            continue
        nk = norm_key(m.group(1).strip())
        st = re.search(r"^subtype:\s*(\S+)", t, re.M)
        rec = pages[nk]
        if st:
            rec["subtype"] = st.group(1)
        for qm in re.finditer(r"^> (.+?)（(ch\d+)）", t, re.M):
            if len(rec["q"]) < MAX_Q:
                rec["q"].append({"ep": qm.group(2), "q": qm.group(1)[:QLEN]})

    # 対象 = 台帳外面（events ∪ pages）+ 既存台帳の所有形 aspect 候補
    targets = set()
    for nk in usage:
        if nk not in known:
            targets.add(nk)
    for nk in pages:
        if nk not in known:
            targets.add(nk)
    aspect_existing = []
    for e in ents:
        c = e["canonical"]
        for m in re.finditer(r"^(.+?)の(正体|心|姿|能力|役割|真の|本名)", c):
            pn = norm_key(m.group(1))
            if pn in known:
                aspect_existing.append(e["canonical"])
                targets.add(nk_norm(c) if False else norm_key(c))

    def parent_cands(nk_disp):
        cands = []
        for m in re.finditer(r"^(.+?)の", nk_disp):
            pn = norm_key(m.group(1))
            if pn in known:
                cands.append(known[pn])
        return cands[:3]

    inv_rows, queue_rows = [], []
    for nk in sorted(targets):
        disp = max([nk] + list(pages.get(nk, {}).get("surfaces", [])), key=len)
        row = {
            "norm": nk,
            "events_count": usage.get(nk, 0),
            "entity_type_votes": dict(etype.get(nk, {})),
            "page_subtype": pages.get(nk, {}).get("subtype", ""),
            "episodes": sorted(eps.get(nk, []))[:6],
            "quotes": (pages.get(nk, {}).get("q") or quotes.get(nk, []))[:MAX_Q],
            "in_ledger": nk in known,
            "parent_candidates": parent_cands(nk),
            "surfaces": sorted(surfaces.get(nk, set()), key=len, reverse=True)[:5],
        }
        inv_rows.append(row)
    (OUT / "v3-inventory.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in inv_rows),
        encoding="utf-8")
    # queue: 6 面 1 群にまとめて 1 行
    inv_rows.sort(key=lambda r: -r["events_count"])
    q_rows = []
    for i in range(0, len(inv_rows), 6):
        q_rows.append({"id": "v3:%04d" % (i // 6), "targets": inv_rows[i:i + 6]})
    (OUT / "v3-review-queue.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in q_rows),
        encoding="utf-8")
    print("targets=%d (events-new=%d page-new=%d aspect-candidates-existing=%d) batches=%d"
          % (len(inv_rows),
             sum(1 for r in inv_rows if not r["in_ledger"] and r["events_count"]),
             sum(1 for r in inv_rows if not r["in_ledger"] and not r["events_count"]),
             len(aspect_existing), len(q_rows)))
    print("=== L2 V3 INVENTORY DONE ===")


if __name__ == "__main__":
    main()
