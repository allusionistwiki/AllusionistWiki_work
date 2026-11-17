#!/usr/bin/env python3
"""④ LLM 要約の品質監査 — LLM による全量判定（サンプリングではない）。

全 16,271 群（削除群は固定要約なので自動判定）を、本文を読ませた LLM 判定パスで
「一致 / 一部一致 / 不一致」判定する（生成とは独立した照合パス）。
  来歴: 判定対象は summaries.jsonl の chain_sha1 == 実 chain 本文（全件照合）。
  閾値: 一致+一部一致 99% 以上で PASS（ユーザー台帳基準 2026-11-13）。
  不一致群は flagged.jsonl に列挙 → summarize_yuragi_chains.py --only-file で再要約 → 再監査。
出力: work/yuragi/L0/runs/<rid>_l0saud/{verdicts.jsonl, flagged.jsonl, audit-report.json}
使い方: python scripts/audit_yuragi_summaries.py [--limit N]
"""
import json
import re
import sys
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
JST = timezone(timedelta(hours=9))
TRUNC = 3000
BATCH = 10
THRESHOLD = 0.99

def sha1_bytes(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    return [json.loads(l) for l in rd(p).splitlines() if l.strip()]

def grab_llm():
    cfg = rd(Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/config.yaml"))
    sec = cfg.split("llm:", 1)[1]
    def g(k):
        m = re.search(rf'^\s*{k}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', sec, re.M)
        return m.group(1).strip()
    return g("base_url"), g("api_key"), g("model")

def load_pairs():
    latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    units = {u["unit_id"]: u for u in jl(L0 / "runs" / latest / "units.jsonl")}
    by_chain = {}
    sdirs = sorted(p for p in (L0 / "runs").iterdir() if p.name.endswith("_l0sum"))
    for sd in sdirs:  # 古い順に流し込み→同一 chain は新しい run が優先
        for s in jl(sd / "summaries.jsonl"):
            by_chain[s["chain_id"]] = s
    sdir_name = "+".join(sd.name for sd in sdirs[-3:])
    pairs = []
    for uid, u in units.items():
        if u["source"] == "jbbs":
            d = RAW / u["raw_path"].rsplit("/", 1)[0]
        elif u["source"] == "mixi":
            d = RAW / "mixi/373088" / u["title"]
        else:
            d = RAW / "hatena_flicker"
        sb = {r["post_no"]: r["body"] for r in jl(d / "structured.jsonl")}
        for c in jl(d / "chains.jsonl"):
            text = "\n\n".join(sb[n] for n in c["post_nos"])
            pairs.append((c, text, by_chain.get(c["chain_id"])))
    return pairs, sdir_name, latest

def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    rid = datetime.now(JST).strftime("%Y%m%dT%H%M") + "_l0saud"
    if "--run-dir" in sys.argv:
        rid = Path(sys.argv[sys.argv.index("--run-dir") + 1]).name
    run = L0 / "runs" / rid
    run.mkdir(parents=True, exist_ok=True)
    judged_p = run / "judged.jsonl"
    done_ids = {v["chain_id"] for v in jl(judged_p)} if judged_p.exists() else set()
    pairs, sdir_name, l0_run = load_pairs()

    from openai import OpenAI
    base_url, api_key, model = grab_llm()
    client = OpenAI(base_url=base_url, api_key=api_key, timeout=900)

    verdicts, flagged, unresolved, sha_bad = [], [], [], []
    todo = []
    for c, text, s in pairs:
        cid = c["chain_id"]
        if s is None:
            flagged.append(cid)
            verdicts.append({"chain_id": cid, "verdict": "不一致", "why": "要約なし"})
            continue
        if sha1_bytes(text.encode("utf-8")) != s["chain_sha1"]:
            sha_bad.append(cid)
            flagged.append(cid)
            verdicts.append({"chain_id": cid, "verdict": "不一致", "why": "sha 不一致"})
            continue
        if c["kind"] == "deleted":
            v = "一致" if s["summary"] == "（削除投稿）" else "不一致"
            verdicts.append({"chain_id": cid, "verdict": v, "why": "削除固定"})
            if v == "不一致":
                flagged.append(cid)
            continue
        todo.append((c, text, s))
    if limit:
        todo = todo[:limit]

    def judge_batch(batch):
        lines = ["次の番号つきの「本文」に対する「要約」の品質を判定してください。",
                 "判定は 一致 / 一部一致 / 不一致 だけ（要点を拾っているか、中心的な事実のズレがないか）。",
                 "形式は「番号: 判定」の行のみ。"]
        for j, (c, text, s) in enumerate(batch):
            tt = text[:TRUNC] + ("…（後略）" if len(text) > TRUNC else "")
            lines.append(f"--- {j}")
            lines.append(f"本文: {tt}")
            lines.append(f"要約: {s['summary']}")
        prompt = "\n".join(lines)
        res = {}
        for attempt in range(5):
            try:
                r = client.chat.completions.create(
                    model=model, temperature=1.0, max_tokens=3000,
                    messages=[{"role": "user", "content": prompt}], stream=False)
                ch = r.choices[0]
                out = getattr(getattr(ch, "message", None), "content", None) or getattr(ch, "content", "")
                for ln in (out or "").splitlines():
                    m = re.match(r"^\s*(\d{1,2})\s*[：:.、]\s*(一致|一部一致|不一致)", ln.strip())
                    if m and 0 <= int(m.group(1)) < len(batch):
                        res[int(m.group(1))] = m.group(2)
                if len(res) == len(batch):
                    return res
                batch = [batch[i] for i in range(len(batch)) if i not in res]
                lines2 = lines[:3]
                for j, (c, text, s) in enumerate(batch):
                    tt = text[:TRUNC] + ("…（後略）" if len(text) > TRUNC else "")
                    lines2.append(f"--- {j}")
                    lines2.append(f"本文: {tt}")
                    lines2.append(f"要約: {s['summary']}")
                prompt = "\n".join(lines2)
            except Exception as e:
                print(f"  judge retry {attempt + 1}: {e}", file=sys.stderr)
        return res

    n = len(todo)
    todo = [x for x in todo if x[0]["chain_id"] not in done_ids]
    def emit_judged(rows):
        with judged_p.open("a", encoding="utf-8", newline="\n") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for i in range(0, len(todo), BATCH):
        batch = todo[i:i + BATCH]
        res = judge_batch(batch)
        rows = []
        for j, (c, text, s) in enumerate(batch):
            v = res.get(j)
            if v is None:
                row = {"chain_id": c["chain_id"], "verdict": "未判定"}
            else:
                row = {"chain_id": c["chain_id"], "verdict": v, "model": model}
            rows.append(row)
        emit_judged(rows)
        verdicts.extend(rows)
        if (i // BATCH) % 20 == 0:
            print(f"judge {min(i + BATCH, len(todo))}/{len(todo)}", file=sys.stderr)

    allrows = {v["chain_id"]: v for v in jl(judged_p)}
    for v in verdicts:
        allrows[v["chain_id"]] = v
    verdicts = list(allrows.values())
    n_ok = sum(1 for v in verdicts if v["verdict"] == "一致")
    n_part = sum(1 for v in verdicts if v["verdict"] == "一部一致")
    n_no = sum(1 for v in verdicts if v["verdict"] == "不一致")
    n_un = sum(1 for v in verdicts if v["verdict"] == "未判定")
    judged = n_ok + n_part + n_no
    rate = (n_ok + n_part) / judged if judged else 0.0
    flagged = sorted({v["chain_id"] for v in verdicts if v["verdict"] in ("不一致", "未判定")})
    counters = {"chains": len(pairs), "judged": judged, "一致": n_ok, "一部一致": n_part,
                "不一致": n_no, "未判定": n_un, "sha_bad": len(sha_bad),
                "pass_rate": round(rate, 4)}
    (run / "verdicts.jsonl").write_text(
        "".join(json.dumps(v, ensure_ascii=False) + "\n" for v in verdicts),
        encoding="utf-8", newline="\n")
    (run / "flagged.jsonl").write_text(
        "".join(json.dumps({"chain_id": cid}, ensure_ascii=False) + "\n" for cid in flagged),
        encoding="utf-8", newline="\n")
    passed = rate >= THRESHOLD and n_un == 0
    report = {
        "audit_of": {"sum_run": sdir_name, "l0_run": l0_run},
        "method": f"LLM 全量判定（生成と独立パス・batch {BATCH}・本文 {TRUNC} 字まで）",
        "threshold": THRESHOLD,
        "counters": counters,
        "passed": passed,
    }
    (run / "audit-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                           encoding="utf-8", newline="\n")
    (run / "run.json").write_text(json.dumps({
        "run_id": rid, "kind": "l0-summary-audit",
        "derived_from": {"sum_run": sdir_name, "l0_run": l0_run},
        "created": datetime.now(JST).isoformat(),
        "result": "PASS" if passed else "ISSUES",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    idx_p = W / "work" / "yuragi" / "index" / "runs-index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8"))
    idx["L0"][rid] = {"status": "current", "kind": "l0-summary-audit",
                      "result": "PASS" if passed else "ISSUES",
                      "path": "work/yuragi/L0/runs/" + rid}
    idx_p.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"SUMMARY-AUDIT {rid} {'PASS' if passed else 'ISSUES'} {json.dumps(counters, ensure_ascii=False)}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
