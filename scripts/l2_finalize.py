"""S3 収束用: 反復 parse 落ちで未裁定のまま残る群に機械フォールバック裁定を書く。

verdict=unknown / kind=機械票（seed prefix > facts 票）/ confidence=要検証。
台帳には載るが review 対象として明示される。既存 adjudications を書き換えない
（adjudications.final.jsonl として追記、S4 の glob でマージされる）。

Usage: python scripts/l2_finalize.py <run_id>
"""
import json
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS, norm_key, load_seed_pages, load_facts, L1_INPUT_RUNS

RUN = sys.argv[1]
OUT = L2_RUNS / RUN


def jl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    queue = jl(OUT / "adjudication-queue.jsonl")
    done = set()
    for p in OUT.glob("adjudications*.jsonl"):
        for d in jl(p):
            done.add(d["id"])

    # facts kind 票
    kind_votes = collections.defaultdict(collections.Counter)
    for d in load_facts(L1_INPUT_RUNS):
        subj = d.get("subject")
        s = ((subj.get("surface") if isinstance(subj, dict) else subj) or "").strip()
        if s and d.get("entity_type"):
            kind_votes[norm_key(s)][d["entity_type"]] += 1

    seeds = {}
    for sd in load_seed_pages().values():
        seeds.setdefault(sd["norm"], []).append(sd)

    out_lines = []
    for row in queue:
        if row["id"] in done:
            continue
        decisions = []
        for m in row["members"]:
            nk = m["norm"]
            votes = kind_votes.get(nk, collections.Counter())
            for sd in seeds.get(nk, []):
                votes[sd["kind"]] += 3
            kind = votes.most_common(1)[0][0] if votes else None
            surfaces = m.get("surfaces") or []
            canonical = max(surfaces, key=lambda s: s.get("count", 0)).get("surface") if surfaces else nk
            decisions.append({"norm": nk, "verdict": "unknown",
                              "canonical": canonical, "kind": kind,
                              "confidence": "要検証",
                              "reason": "mechanical fallback (反復 parse 落ち)"})
        out_lines.append({"id": row["id"], "run": RUN, "decisions": decisions,
                          "group_confidence": "要検証",
                          "summary": "機械フォールバック（人間レビュー対象）"})
    with (OUT / "adjudications.final.jsonl").open("a", encoding="utf-8") as f:
        for l in out_lines:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")
    # 残検証
    done2 = set(done) | {l["id"] for l in out_lines}
    print("finalized=%d remaining_missing=%d" % (len(out_lines), len(queue) - len(done2)))
    print("=== L2 FINALIZE DONE ===")


if __name__ == "__main__":
    main()
