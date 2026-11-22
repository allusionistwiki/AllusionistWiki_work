# -*- coding: utf-8 -*-
"""Lane K4 候補収集: 監査記録中の「作中創作」系 drop 語を全収集し登場例付き dump を作る（非 LLM）。

基準（2026-11-22 ユーザー是正 v0.14）: 一般名詞単体は drop だが、コンテキスト付与の複合語
（精霊魔術・精霊鉄型）や作中人物/国/制度（リクシャマー・アエルガ型）は全て記事化対象。
→ 監査で「作中創作」として drop された語は entities 面の対象。全件收集→実読裁定→seed 注入。
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract_yuragi_allusions as ex

W = Path(ex.__file__).resolve().parent.parent
RUNS = W / "work" / "yuragi" / "L1" / "runs"
OUT = Path(r"C:\Users\d5dx\AppData\Local\hermes\profiles\awiki2\cache\scratch\k4_review.txt")

PAT = re.compile(r"作中(創作|命名|地名|書物|条約|催事|神|民族|技術|实体|世界|名詞|ゲーム|用語|設定)|架空|創作物|設定語|作中人物|作中国")


def jl(p: Path):
    if not p.is_file():
        return []
    out = []
    for l in p.read_bytes().decode("utf-8", "replace").splitlines():
        if not l.strip():
            continue
        try:
            r = json.loads(l)
        except Exception:
            continue
        if isinstance(r, dict) and "_meta" in r:
            continue
        out.append(r)
    return out


def main():
    cands: dict = {}
    # 1) run 側 suppressions（publish が拾っている場所）
    for sp in RUNS.glob("*/suppressions.json"):
        try:
            rows = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in rows:
            t = str(s.get("term", "")).strip()
            r = str(s.get("reason", ""))
            if t and PAT.search(r):
                cands.setdefault(t, []).append(("supp", r[:60]))
    # 2) unit 側 suppressions（raw 配下）
    for jf in (RUNS / "20261122T2200_l1a2b1" / "allusions").glob("gate_audit.jsonl"):
        pass
    for jf in RUNS.glob("*/gate_audit.jsonl"):
        for it in jl(jf):
            t = str(it.get("term", "")).strip()
            r = str(it.get("reason", "")) + " " + str(it.get("usage", ""))
            if t and PAT.search(r):
                cands.setdefault(t, []).append(("gateE", r[:60]))
    for jf in RUNS.glob("*/reaudit.jsonl"):
        for it in jl(jf):
            t = str(it.get("term", "")).strip()
            r = str(it.get("reason", ""))
            st = str(it.get("verdict", it.get("status", "")))
            if t and st.lower().startswith("drop") and PAT.search(r):
                cands.setdefault(t, []).append(("reaudJ", r[:60]))
    for jf in RUNS.glob("*/allusions/gate_drops.jsonl"):
        for it in jl(jf):
            t = str(it.get("term", "")).strip()
            r = str(it.get("reason", it.get("gate", "")))
            if t and PAT.search(r):
                cands.setdefault(t, []).append(("gateD", r[:60]))
    # 既カバー除去
    covered = set()
    for sub in ("entities", "allusion_entities"):
        d = W.parent / "YuragiWiki" / "content" / sub
        if d.is_dir():
            for p in d.glob("*.md"):
                covered.add(ex.norm(p.stem))
    # unit suppressions（YuragiWiki raw 側）
    for sp in (W.parent / "YuragiWiki" / "raw").glob("**/suppressions.json"):
        try:
            rows = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in rows:
            t = str(s.get("term", "")).strip()
            r = str(s.get("reason", ""))
            if t and PAT.search(r):
                cands.setdefault(t, []).append(("unitSupp", r[:60]))
    todo = {t: v for t, v in cands.items() if ex.norm(t) not in covered}
    print(f"[k4] cands={len(cands)} uncovered={len(todo)}")
    # 登場例収集: 全 run の allusions jsonl から usage/quotes を拾う
    usage: dict = {}
    for jf in RUNS.glob("*/allusions/*.jsonl"):
        if jf.stem.startswith(("gate", "audit", "_")):
            continue
        for it in jl(jf):
            t = str(it.get("term", "")).strip()
            if t in todo and t not in usage:
                u = str(it.get("usage", ""))[:150]
                qs = it.get("quotes") or []
                q = ""
                if qs and isinstance(qs[0], dict):
                    q = str(qs[0].get("q", ""))[:120]
                usage[t] = (u, q)
    lines = []
    for t in sorted(todo):
        u, q = usage.get(t, ("", ""))
        why = "; ".join(sorted({v[1] for v in todo[t]}))[:150]
        lines.append(f"### {t}\n裁定根拠: {why}\nusage: {u}\n引用: {q}")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"[k4] dump={len(lines)} -> {OUT}")


if __name__ == "__main__":
    main()
