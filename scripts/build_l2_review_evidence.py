"""S3R: 再裁定用 evidence 生成（P4 v2 — 全話使用状況スキャン＋共起分離信号）。

Usage: python scripts/build_l2_review_evidence.py <run_id>
Input : runs/<id>/adjudication-queue.jsonl + v1 adjudications*.jsonl + L1 facts
Output: runs/<id>/review-evidence.jsonl（1 行 = 1 群の証拠パック）
        runs/<id>/mech-splits.jsonl（同一 fact 共起による機械 split）

各 member: 話をまたいだ使用実 evidence（1 話 1 件・最大 8・fact_type/is_a/quote 110字）
各 pair: 同一 fact 内 subject-object 共起回数（>=2 → 機械 split: 別人の機械的証拠）
"""
import json
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS, norm_key, load_facts, L1_INPUT_RUNS, ep_sort_key

RUN = sys.argv[1]
OUT = L2_RUNS / RUN
MAX_EV = 8          # 1 member あたりの証拠件数（1 話 1 件）
QUOTE_LEN = 110


def jl(p):
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main():
    queue = jl(OUT / "adjudication-queue.jsonl")
    v1 = {}
    for p in sorted(OUT.glob("adjudications*.jsonl")):
        for d in jl(p):
            v1[d["id"]] = d          # 最終ラウンド採用（ファイル名順後勝ち）

    # ---- facts 全量スキャン: norm → 使用実、pair → 共起 -------------------
    usage = collections.defaultdict(dict)          # norm -> ep -> best record
    cooc = collections.Counter()                   # (normA,normB) sorted
    for d in load_facts(L1_INPUT_RUNS):
        subj = d.get("subject")
        s = ((subj.get("surface") if isinstance(subj, dict) else subj) or "").strip()
        if not s:
            continue
        nk = norm_key(s)
        ep = d.get("episode")
        rec = {"ep": ep, "para": d.get("paragraph"),
               "type": d.get("fact_type"), "is_a": d.get("is_a"),
               "q": str(d.get("quote") or "")[:QUOTE_LEN]}
        if ep and ep not in usage[nk]:
            usage[nk][ep] = rec
        obj = d.get("object")
        o = ((obj.get("surface") if isinstance(obj, dict) else obj) or "").strip() \
            if obj else ""
        if o:
            ok = norm_key(o)
            if ok != nk:
                cooc[tuple(sorted((nk, ok)))] += 1

    # ---- 群ごとの証拠パック + 機械 split ----------------------------------
    n_rows = 0
    n_mech_pairs = 0
    with (OUT / "review-evidence.jsonl").open("w", encoding="utf-8") as f, \
         (OUT / "mech-splits.jsonl").open("w", encoding="utf-8") as fs:
        for row in queue:
            members = [m["norm"] for m in row.get("members", [])]
            prev = v1.get(row["id"], {})
            pv = {m.get("norm"): {"verdict": m.get("verdict"),
                                  "canonical": m.get("canonical"),
                                  "confidence": m.get("confidence")}
                  for m in prev.get("decisions", [])}
            # 機械 split: 群内 pair で同一 fact 共起 >= 2
            mech = []
            for i, a in enumerate(members):
                for b in members[i + 1:]:
                    n = cooc.get(tuple(sorted((a, b))), 0)
                    if n >= 2:
                        mech.append({"a": a, "b": b, "same_fact": n})
                        fs.write(json.dumps(
                            {"gid": row["id"], "a": a, "b": b, "same_fact": n,
                             "run": RUN}, ensure_ascii=False) + "\n")
                        n_mech_pairs += 1
            pack = {"id": row["id"], "edge_types": row.get("edge_types", []),
                    "prev": pv, "mech_split": mech, "members": []}
            for m in row.get("members", []):
                nk = m["norm"]
                evs = sorted(usage.get(nk, {}).values(),
                             key=lambda r: ep_sort_key(r["ep"] or ""))
                if len(evs) > MAX_EV:
                    idx = [round(i * (len(evs) - 1) / (MAX_EV - 1))
                           for i in range(MAX_EV)] if len(evs) > MAX_EV else range(len(evs))
                    evs = [evs[i] for i in sorted(set(idx))]
                pack["members"].append({
                    "norm": nk,
                    "count": m.get("count", 0),
                    "surfaces": [s.get("surface") for s in (m.get("surfaces") or [])[:3]],
                    "evidence": evs,
                })
            f.write(json.dumps(pack, ensure_ascii=False) + "\n")
            n_rows += 1
    print("rows=%d mech_split_pairs=%d usage_norms=%d cooc_pairs=%d"
          % (n_rows, n_mech_pairs, len(usage), len(cooc)))
    print("=== L2 REVIEW EVIDENCE DONE ===")


if __name__ == "__main__":
    main()
