#!/usr/bin/env python3
"""Yuragi L1 篇記事 品質監査（二層）— 機械ゲート＋LLM 全量監査（生成独立パス）。

機械ゲート: 記事内の引用「…」が実在するか（コーパス本文との部分文字列照合・改行/空白正規化）、
            引用 100 字超なし、規定見出し 4 個presence。
LLM 監査: 記事全文＋群索引＋本文（1 群あたり --max 字に正規化）を読みさせ
          「概要・流れ・設定・引用がコーパスに忠実か」を 一致/一部一致/不一致 で判定。
出力: work/yuragi/L1/runs/<rid>_l1aud/ {verdicts.jsonl, flagged.jsonl, audit.json}
不合格は記事 md を削除して build_yuragi_l1.py resume で再生成 → 再監査。
使い方: python scripts/audit_yuragi_l1.py [--workers K] [--max N] [--run-dir rid]
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

W = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistWiki_work")
RAW = Path(r"C:/Users/d5dx/Downloads/Code/YuragiWiki") / "raw" / "bbs"
L0 = W / "work" / "yuragi" / "L0"
L1 = W / "work" / "yuragi" / "L1"
THRESHOLD = 1.0

def rd(p: Path) -> str:
    return p.read_bytes().decode("utf-8", errors="replace")

def jl(p: Path):
    out = []
    for l in rd(p).splitlines():
        if not l.strip():
            continue
        r = json.loads(l)
        if isinstance(r, dict) and r.get("_meta"):
            continue
        out.append(r)
    return out

def load_llm_config():
    cfg = Path(r"C:/Users/d5dx/Downloads/Code/AllusionistLLMWiki2/config.yaml").read_text(encoding="utf-8")
    sec = cfg.split("llm:", 1)[1]
    def grab(key):
        m = re.search(rf'^\s*{key}:\s*"?([^"#\n]+?)"?\s*(#.*)?$', sec, re.M)
        return m.group(1).strip() if m else None
    return {"base_url": grab("base_url").rstrip("/"), "api_key": grab("api_key"), "model": grab("model")}

CFG = load_llm_config()

def call_llm(prompt: str, max_tokens: int = 3000) -> str:
    body = json.dumps({
        "model": CFG["model"],
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0, "max_tokens": max_tokens, "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                CFG["base_url"] + "/chat/completions", data=body,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {CFG['api_key']}"})
            resp = json.loads(urllib.request.urlopen(req, timeout=600).read().decode("utf-8"))
            ch = resp["choices"][0]
            txt = (ch.get("message") or {}).get("content") or ch.get("content") or ""
            if txt.strip():
                return txt.strip()
        except Exception:
            pass
        time.sleep(2 + 3 * attempt)
    return ""

def unit_dir(u):
    if u["source"] == "jbbs":
        return RAW / u["raw_path"].rsplit("/", 1)[0]
    if u["source"] == "mixi":
        return RAW / "mixi/373088" / u["title"]
    return RAW / "hatena_flicker"

def norm(s: str) -> str:
    return re.sub(r"[\s\u3000,、,]+", "", s)

ELLIPSIS = re.compile(r"…+|\.\.\.+|⋯+")

def quote_in(q: str, *corpora: str) -> bool:
    """引用がコーパスの連続部分文字列か。省略記号（…/...）を含む場合は
    分節し、各分節が順にコーパスに存在すれば許容（原文の省略引用）。"""
    if any(q in c for c in corpora):
        return True
    segs = [s for s in ELLIPSIS.split(q) if s]
    if len(segs) >= 2:
        for c in corpora:
            pos = 0
            ok = True
            for s in segs:
                i = c.find(s, pos)
                if i < 0:
                    ok = False
                    break
                pos = i + len(s)
            if ok:
                return True
    return False

HEADS = ["## 概要", "## 流れ", "## 主要な話題・設定", "## 注目投稿"]

def mech_gate(uid, art, body_all, chain_summaries=""):
    issues = []
    body_n = norm(body_all)
    summ_n = norm(chain_summaries)
    # 引用照合は「注目投稿」欄のみ。照合対象 = 原文全文 ∪ 群索引の要約（記事生成時に提示済みの正準文）。
    m = re.search(r"##\s*注目投稿(.*?)(?=\n##|\Z)", art, re.S)
    sec = m.group(1) if m else ""
    for q in re.findall(r"「([^」]+)」", sec):
        if len(q) > 100:
            issues.append(f"{uid}:QUOTE_LONG:{len(q)}")
        elif not quote_in(norm(q), body_n, summ_n):
            issues.append(f"{uid}:QUOTE_NOTFOUND:{q[:30]}")
    for h in HEADS:
        if h not in art:
            issues.append(f"{uid}:HEAD_MISSING:{h}")
    return issues

def judge(uid, title, art, chains, posts, mx):
    by_no = {p["post_no"]: p for p in posts}
    lines = [f"=== 記事（{title}） ===", art, "", "=== 群索引 ==="]
    for c in chains:
        t = ",".join(c.get("topics", [])) or "—"
        lines.append(f"{c['chain_id'].split('#')[1]} [{c['post_range'][0]}-{c['post_range'][1]}] "
                     f"{c['author']} 話題:{t} 要約: {c.get('summary','')}")
    lines.append("")
    lines.append("=== コーパス本文（抜粋） ===")
    for c in chains:
        txt = "\n".join(by_no[n]["body"] for n in c["post_nos"] if n in by_no)
        lines.append(f"[g{c['chain_id'].split('#')[1]}] {txt[:mx]}")
    lines += ["", "判定任务: この L1 記事はコーパスに忠実か。",
              "- 概要/流れ/設定が本文事実と一致しているか（文中に無い創作がないか）",
              "- 引用が実在し文脈を曲げていないか",
              "- 群番号参照が群索引と矛盾しないか",
              '出力: 「判定: 一致」/「判定: 一部一致」/「判定: 不一致」の 1 行目＋2 行目に理由 1 文']
    out = call_llm("\n".join(lines))
    m = re.search(r"判定[:：]\s*(一致|一部一致|不一致)", out)
    verdict = m.group(1) if m else "未判定"
    reason = out.splitlines()[1].strip() if len(out.splitlines()) > 1 else out[:80]
    return verdict, reason

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--run-dir", default=None)
    a = ap.parse_args()

    l1_rid = (L1 / "latest.txt").read_text(encoding="utf-8").strip()
    arts = {}
    for p in sorted((L1 / "runs" / l1_rid / "units").glob("*.md")):
        arts[p.stem] = p.read_text(encoding="utf-8")
    l0_latest = (L0 / "latest.txt").read_text(encoding="utf-8").strip()
    urows, seen = [], set()
    for u in jl(L0 / "runs" / l0_latest / "units.jsonl"):
        if u["unit_id"] not in seen:
            seen.add(u["unit_id"])
            urows.append(u)

    rid = a.run_dir or (dt.datetime.now().strftime("%Y%m%dT%H%M") + "_l1aud")
    out = L1 / "runs" / rid
    out.mkdir(parents=True, exist_ok=True)
    done = {}
    jf = out / "judged.jsonl"
    if jf.exists():
        for r in jl(jf):
            done[r["unit_id"]] = r

    def work(u):
        uid = u["unit_id"]
        if uid in done:
            return
        art = arts.get(uid)
        if not art:
            with jf.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id": uid, "verdict": "未判定",
                                    "reason": "記事なし"}, ensure_ascii=False) + "\n")
            return
        body_md = re.sub(r"^---.*?---\s*", "", art, count=1, flags=re.S)
        d = unit_dir(u)
        chains = jl(d / "chains.jsonl")
        posts = jl(d / "structured.jsonl")
        body_all = "\n".join(p["body"] for p in posts)
        sums = "\n".join(c.get("summary", "") for c in chains)
        mech = mech_gate(uid, body_md, body_all, sums)
        verdict, reason = judge(uid, u["title"], body_md, chains, posts, a.max)
        if mech:
            verdict = "不一致"
            reason = "機械ゲート: " + "; ".join(mech[:3])
        with jf.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id": uid, "verdict": verdict, "reason": reason,
                                "model": CFG["model"], "ts": dt.datetime.now().isoformat()},
                               ensure_ascii=False) + "\n")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(work, urows))

    rows = {r["unit_id"]: r for r in jl(jf)}
    # 機械ゲートは決定論なので、LLM 判定済み行にも常に再適用する（judged 再利用の高速再監査）
    for u in urows:
        r = rows.get(u["unit_id"])
        if not r or r["reason"].startswith("機械ゲート") or r["verdict"] == "未判定":
            continue
        art = arts.get(u["unit_id"])
        if not art:
            continue
        body_md = re.sub(r"^---.*?---\s*", "", art, count=1, flags=re.S)
        d = unit_dir(u)
        body_all = "\n".join(p["body"] for p in jl(d / "structured.jsonl"))
        sums = "\n".join(c.get("summary", "") for c in jl(d / "chains.jsonl"))
        mech = mech_gate(u["unit_id"], body_md, body_all, sums)
        if mech:
            r["verdict"] = "不一致"
            r["reason"] = "機械ゲート: " + "; ".join(mech[:3])
            with jf.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            rows[u["unit_id"]] = r
    counts = {}
    for r in rows.values():
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    n = len(rows)
    ok = counts.get("一致", 0) + counts.get("一部一致", 0)
    rate = ok / n if n else 0.0
    flagged = [r["unit_id"] for r in rows.values() if r["verdict"] not in ("一致", "一部一致")]
    (out / "flagged.jsonl").write_text("".join(u + "\n" for u in flagged), encoding="utf-8")
    passed = rate >= THRESHOLD and len(flagged) == 0
    (out / "audit.json").write_text(json.dumps({
        "run_id": rid, "l1_run": l1_rid, "articles": n, "counts": counts,
        "pass_rate": round(rate, 4), "flagged": len(flagged), "model": CFG["model"]},
        ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"L1-AUDIT {rid} {'PASS' if passed else 'ISSUES'} flagged={len(flagged)} "
          f"rate={rate:.4f} {json.dumps(counts, ensure_ascii=False)}")
    return 0 if passed else 1

if __name__ == "__main__":
    sys.exit(main())
