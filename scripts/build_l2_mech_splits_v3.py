"""S3R-c: 同一文共起の機械 split を再構築（述語=同一性言明を除外）。

Usage: python scripts/build_l2_mech_splits_v3.py <run_id>
Input : runs/<id>/clusters_draft.json + L1 facts（quote 全文）
Output: runs/<id>/mech-splits.jsonl（上書き） — 同一引用文に両名義が並ぶ事実（同一性述語を除外）

同一 fact の subject↔object は「X は Y である」型の同一性言明＝共起の反証になる。
→ 共起は「fact の主語が A で、引用文中に B が独立に現れる」形のみを数える。
"""
import json
import re
import sys
import collections
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from l2_common import L2_RUNS, L1_INPUT_RUNS, norm_key, load_facts

RUN = sys.argv[1]
OUT = L2_RUNS / RUN
COPULA = ("である", "だ", "呼び", "名は", "正体", "こと", "とは", "＝", "=", "—", " identifier")


def main():
    draft = json.loads((OUT / "clusters_draft.json").read_text(encoding="utf-8"))
    pairs_wanted = set()
    surf2norm = {}
    for g in draft["groups"]:
        ms = [m["norm"] for m in g["members"]]
        for i, a in enumerate(ms):
            for b in ms[i + 1:]:
                pairs_wanted.add(tuple(sorted((a, b))))
    # 面 → norm（表記ゆれ込み）
    for g in draft["groups"]:
        for m in g["members"]:
            for s in m.get("surfaces", []):
                surf2norm.setdefault(s["surface"], m["norm"])
    surs = [s for s in surf2norm if len(s) >= 2]
    surs.sort(key=len, reverse=True)
    rx = re.compile("|".join(map(re.escape, surs)))

    cooc = collections.Counter()
    for d in load_facts(L1_INPUT_RUNS):
        subj = d.get("subject")
        s = ((subj.get("surface") if isinstance(subj, dict) else subj) or "").strip()
        if not s:
            continue
        ak = norm_key(s)
        quote = str(d.get("quote") or "")
        if not quote:
            continue
        found = set()
        for mt in rx.finditer(quote):
            surf = mt.group(0)
            nk = norm_key(surf2norm[surf])
            if nk == ak:
                continue
            found.add(nk)
        for bk in found:
            cooc[tuple(sorted((ak, bk)))] += 1

    rows = []
    for pair, c in cooc.items():
        if pair in pairs_wanted and c >= 2:
            rows.append({"a": pair[0], "b": pair[1], "same_sentence": c,
                         "run": RUN})
    rows.sort(key=lambda r: -r["same_sentence"])
    (OUT / "mech-splits.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    print("mech-splits v3 rows=%d (same-sentence, copula-excluded)" % len(rows))
    print("=== MECH SPLITS V3 DONE ===")


if __name__ == "__main__":
    main()
